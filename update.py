import requests
from bs4 import BeautifulSoup
import feedgenerator
from datetime import datetime, timezone
import re
import os
import json
import time
from urllib.parse import urljoin, urlparse
import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramRSSGenerator:
    def __init__(self, config_file='list.json'):

        self.config_file = config_file
        self.base_url = 'https://t.me/s/'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        })
        
        # dirs for RSS
        os.makedirs('rss_feeds', exist_ok=True)
        os.makedirs('channel_data', exist_ok=True)

        # config upload
        self.channels = self.load_channels_config()

    def load_channels_config(self):

        default_config = {"channels": []}
        
        if not os.path.exists(self.config_file):
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            logger.info(f"Self config created: {self.config_file}")
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    # initialized flags
    def get_init_flag_file(self, channel_name):
        return f"channel_data/.{channel_name}_initialized"
    
    def is_channel_initialized(self, channel_name):
        flag_file = self.get_init_flag_file(channel_name)
        return os.path.exists(flag_file)
    
    def mark_channel_initialized(self, channel_name):
        flag_file = self.get_init_flag_file(channel_name)
        with open(flag_file, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())
        logger.info(f"✓ Channel {channel_name} marked as initialized")
    
    # scrape with scrolling (for new channels)     
    def scrape_channel_messages_with_scroll(self, channel_name, limit=30, channel_config=None):

        url = f"{self.base_url}{channel_name}"
        messages = []
        
        try:
            logger.info(f"[] Scraping with scroll: {channel_name} (target: {limit})")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    'User-Agent': self.session.headers['User-Agent']
                })
                
                page.goto(url)
                page.wait_for_timeout(2000)  
                
                # scrolling
                for scroll_num in range(15):  
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(1500)
                    
                    # message counter
                    soup = BeautifulSoup(page.content(), 'html.parser')
                    widgets = soup.find_all('div', class_='tgme_widget_message')
                    
                    logger.info(f"  Scroll {scroll_num + 1}: {len(widgets)} messages loaded")
                    
                    # Еstop logic after limit
                    if len(widgets) >= limit:
                        break
                
                # parsing
                html = page.content()
                browser.close()
                soup = BeautifulSoup(html, 'html.parser')
                message_widgets = soup.find_all('div', class_='tgme_widget_message')
                
                # take newest
                for widget in message_widgets[-limit:]:
                    try:
                        message_data = self.parse_message_widget(widget, channel_name, channel_config)
                        if message_data:
                            messages.append(message_data)
                    except Exception as e:
                        logger.warning(f"Parsing error: {e}")
                        continue

                logger.info(f"✓ Collected {len(messages)} messages from {channel_name}")
            
        except Exception as e:
            logger.error(f"! Error scraping {channel_name}: {e}")
        
        return messages 
       
    # quick scraping w/ scrolling
    def scrape_channel_messages_quick(self, channel_name, limit=5, channel_config=None):

        url = f"{self.base_url}{channel_name}"
        messages = []
        
        try:
            logger.info(f" Quick scraping: {channel_name} (limit: {limit})")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_widgets = soup.find_all('div', class_='tgme_widget_message')
            
            # newest
            for widget in message_widgets[-limit:]:
                try:
                    message_data = self.parse_message_widget(widget, channel_name, channel_config)
                    if message_data:
                        messages.append(message_data)
                except Exception as e:
                    logger.warning(f"Parsing error: {e}")
                    continue

            logger.info(f"✓ Quick collected {len(messages)} messages from {channel_name}")
            
        except Exception as e:
            logger.error(f"! Error in quick scraping {channel_name}: {e}")
        
        return messages
    
    def parse_message_widget(self, widget, channel_name, channel_config=None):
        try:
            # message ID
            message_link = widget.find('a', class_='tgme_widget_message_date')
            if not message_link:
                return None
                
            message_id = message_link.get('href', '').split('/')[-1]
            if not message_id:
                # ID backup
                import uuid
                message_id = str(uuid.uuid4())
                logger.warning(f"!!! Empty ID, generated: {message_id}")
            
            # date of publish
            datetime_elem = widget.find('time')
            if datetime_elem:
                datetime_str = datetime_elem.get('datetime')
                if datetime_str:
                    pub_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                else:
                    pub_date = datetime.now(timezone.utc)
            else:
                pub_date = datetime.now(timezone.utc)
            
            # message text
            text_elem = widget.find('div', class_='tgme_widget_message_text')
            if text_elem:
                # replaced <br> with \n 
                for br in text_elem.find_all('br'):
                    br.replace_with('\n')
                
                # no sep
                text = text_elem.get_text(strip=False)
                
                # normalize
                lines = [line.strip() for line in text.split('\n')]
                text = '\n'.join(line for line in lines if line)  # deleting empty strings
            else:
                text = ""
            # sanitize secrets
            text = self.sanitize_sensitive_data(text)

            # title catching
            title = self.extract_first_line_title(text, message_id, channel_config)
            
            # message link
            link = f"https://t.me/{channel_name}/{message_id}"
            
            # media catch
            media_info = self.extract_media_info(widget)
            if media_info:
                text += f"\n\n[Media: {media_info}]"
            
            return {
                'id': message_id,
                'title': title,
                'text': text,
                'link': link,
                'pub_date': pub_date,
                'channel': channel_name
            }
            
        except Exception as e:
            logger.warning(f"! Message parsing error: {e}")
            return None

    # ID used for fallback    
    def extract_first_line_title(self, text, message_id, channel_config=None):

        if not text or not text.strip():
            return f"Message {message_id}"
        
        # split text to lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return f"Message {message_id}"
        
        # whitch line to title (from cfg)
        title_line_index = 0
        if channel_config and 'title_line' in channel_config:
            title_line_index = channel_config['title_line']
        
        if 0 <= title_line_index < len(lines):
            first_line = lines[title_line_index]
        else:
            first_line = lines[0]
        
        # strip length 
        max_length = 200
        if len(first_line) <= max_length:
            return first_line
        else:
            # strip by space
            cut_pos = first_line.rfind(' ', 0, max_length)
            if cut_pos > max_length * 0.8:
                return first_line[:cut_pos] + "..."
            else:
                return first_line[:max_length-3] + "..."
            
    def extract_media_info(self, widget):
        media_types = []
        
        # images
        if widget.find('a', class_='tgme_widget_message_photo_wrap'):
            media_types.append('Фото')
        
        # video
        if widget.find('video') or widget.find('i', class_='tgme_widget_message_video_player'):
            media_types.append('Видео')
        
        # docs
        if widget.find('div', class_='tgme_widget_message_document'):
            media_types.append('Документ')
        
        # audio
        if widget.find('audio') or widget.find('div', class_='tgme_widget_message_voice'):
            media_types.append('Аудио')
        
        return ', '.join(media_types) if media_types else None

    def sanitize_sensitive_data(self, text, channel_name=""):
        if not text:
            return text
        
        original_text = text
        redactions = {}
        
        patterns = {
            'AWS_ACCESS_KEY': r'AKIA[0-9A-Z]{16}',
            'AWS_SECRET': r'(?<![A-Za-z0-9/+])(?:[A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])',
            'PRIVATE_KEY': r'-----BEGIN [A-Z ]*KEY.*?-----END [A-Z ]*KEY.*?-----',
            'TELEGRAM_BOT_TOKEN': r'\d{8,12}:[A-Za-z0-9_-]{25,}',
            'JWT_TOKEN': r'eyJ[A-Za-z0-9_-]+\.(?:[A-Za-z0-9_-]+\.)?[A-Za-z0-9_-]+',
            'STRIPE_KEY': r'(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{20,}',
            'MONGODB_URI': r'mongodb\+srv://[^\s:]+:[^\s@]+@',
            'DATABASE_URL': r'(?:postgres|mysql|sqlite)://[^\s:]+:[^\s@]+@',
        }
        
        for pattern_name, pattern in patterns.items():
            matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                found_value = match.group()
                replacement = f'[REDACTED_{pattern_name}]'
                text = text.replace(found_value, replacement, 1)
                
                if pattern_name not in redactions:
                    redactions[pattern_name] = 0
                redactions[pattern_name] += 1
        
        # logs
        if redactions:
            redaction_list = ', '.join([f"{k}({v})" for k, v in redactions.items()])
            logger.warning(f"!!! {channel_name}: Redacted sensitive data - {redaction_list}")
        
        return text
 
    def generate_rss_feed(self, channel_config, messages):
        
        channel_name = channel_config['name']
        rss_filename = f"rss_feeds/{channel_name}.xml"
        data_filename = f"channel_data/{channel_name}.json"
        
        # collecting
        all_messages = list(messages)
        
        # cheking json
        if os.path.exists(data_filename):
            try:
                with open(data_filename, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                
                for old_msg in old_data.get('messages', []):
                    all_messages.append({
                        'id': old_msg['id'],
                        'title': old_msg['title'],
                        'text': old_msg['text'],
                        'link': old_msg['link'],
                        'pub_date': datetime.fromisoformat(old_msg['pub_date']),
                        'channel': channel_name
                    })
                
                logger.info(f"✓ Added {len(old_data.get('messages', []))} old messages")
            except Exception as e:
                logger.warning(f"Could not read old data: {e}")
        
        # deleting dupl
        unique_messages = {}
        for msg in all_messages:
            if msg['id'] not in unique_messages:
                unique_messages[msg['id']] = msg
        
        # RSS with Atom namespace
        feed = feedgenerator.Rss201rev2Feed(
            title=channel_config.get('title', f"Channel @{channel_name}"),
            link=f"https://t.me/{channel_name}",
            description=channel_config.get('description', f"RSS of @{channel_name}"),
            language='ru',
            lastBuildDate=datetime.now(timezone.utc),
        )
 
        # atom:link for self-reference        
        feed.feed['atom_link'] = {
            'href': f"https://<user_name>.github.io/<rep_name>/{channel_name}.xml",
            'rel': 'self',
            'type': 'application/rss+xml'
        }
        
        sorted_msgs = sorted(
            unique_messages.values(),
            key=lambda x: int(x['id']),
            reverse=True
        )
       # add to feed        
        for message in sorted_msgs:
            feed.add_item(
                title=message['title'],
                link=message['link'],
                description=message['text'],
                pubdate=message['pub_date'],
                unique_id=f"telegram_{channel_name}_{message['id']}",
                unique_id_is_permalink=False
            )
        
        with open(rss_filename, 'w', encoding='utf-8') as f:
            feed.write(f, 'utf-8')
        
        logger.info(f"✓ RSS: {len(unique_messages)} total items")
        return rss_filename

    # saving data
    def save_channel_data(self, channel_name, messages):
        
        data_filename = f"channel_data/{channel_name}.json"
        
        # old data
        old_messages = []
        if os.path.exists(data_filename):
            try:
                with open(data_filename, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                old_messages = old_data.get('messages', [])
            except:
                pass
        
        # id dict 
        all_msgs_dict = {}
        
        for msg in old_messages:
            all_msgs_dict[msg['id']] = msg
        
        for msg in messages:
            all_msgs_dict[msg['id']] = {
                'id': msg['id'],
                'title': msg['title'],
                'text': msg['text'],
                'link': msg['link'],
                'pub_date': msg['pub_date'].isoformat()
            }
        
        # sorting
        sorted_msgs = sorted(
            all_msgs_dict.values(),
            key=lambda x: x['pub_date'],
            reverse=True
        )
        
        # saving
        data = {
            'channel': channel_name,
            'last_update': datetime.now(timezone.utc).isoformat(),
            'messages_count': len(sorted_msgs),
            'messages': sorted_msgs
        }
        
        with open(data_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✓ Data: {len(sorted_msgs)} total items")

    def update_all_channels(self):

        logger.info("=" * 50)
        logger.info("Updating started...")
        logger.info("=" * 50)
        
        for channel_config in self.channels['channels']:
            channel_name = channel_config['name']
            
            try:
                # checking for initialize
                if self.is_channel_initialized(channel_name):
                    # quick logic
                    limit = channel_config.get('regular_limit', 5)
                    logger.info(f"\n{channel_name} [KNOWN CHANNEL]")
                    logger.info(f"  Mode: Quick update (limit: {limit})")
                    
                    messages = self.scrape_channel_messages_quick(
                        channel_name, 
                        limit, 
                        channel_config
                    )
                else:
                    # new channel - full scrape
                    limit = channel_config.get('initial_limit', 30)
                    logger.info(f"\n{channel_name} [NEW CHANNEL]")
                    logger.info(f"  Mode: Initial pull with scroll (limit: {limit})")
                    
                    messages = self.scrape_channel_messages_with_scroll(
                        channel_name, 
                        limit, 
                        channel_config
                    )
                
                # saving
                if messages:
                    rss_file = self.generate_rss_feed(channel_config, messages)
                    self.save_channel_data(channel_name, messages)
                    
                    # flag of inicialization changes
                    if not self.is_channel_initialized(channel_name):
                        self.mark_channel_initialized(channel_name)
                    
                    logger.info(f"✓ {channel_name} processed successfully ({len(messages)} messages)\n")
                else:
                    logger.warning(f"WARNING  {channel_name} - no messages collected\n")
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"! Error processing {channel_name}: {e}\n")
        
        logger.info("=" * 50)
        logger.info("Update finished!")
        logger.info("=" * 50)

    def get_rss_urls(self):
        rss_urls = []
        
        for channel_config in self.channels['channels']:
            channel_name = channel_config['name']
            rss_file = f"rss_feeds/{channel_name}.xml"
            
            if os.path.exists(rss_file):
                local_url = f"file:///{os.path.abspath(rss_file)}"
                rss_urls.append({
                    'channel': channel_name,
                    'title': channel_config.get('title', channel_name),
                    'local_file': rss_file,
                    'local_url': local_url
                })
        
        return rss_urls


def main():

    print("=== RSS Generator ===")
    print()
    
    generator = TelegramRSSGenerator()
    generator.update_all_channels()
    
    print("\n=== Created RSS feeds ===")
    rss_urls = generator.get_rss_urls()
    
    if rss_urls:
        for rss_info in rss_urls:
            print(f"Channel: {rss_info['title']}")
            print(f"  File: {rss_info['local_file']}")
            print(f"  URL: {rss_info['local_url']}")
            print()
        
    else:
        print("!!!WARNING RSS creation failed.")


if __name__ == "__main__":
    main()
