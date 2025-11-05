import json
from datetime import datetime, timezone, timedelta
import os


def build_html_page():
    settings_file = 'list.json'
    destination_dir = 'gh-pages'
    
    with open(settings_file, 'r', encoding='utf-8') as config_data:
        registry = json.load(config_data)

    tz_offset = timezone(timedelta(hours=3))
    timestamp_str = datetime.now(tz_offset).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    entries_markup = ""
    for entry in registry['channels']:
        feed_name = entry['name']
        feed_label = entry['title']
        entries_markup += f'                  <li><a href="{feed_name}.xml">{feed_label}</a></li>\n'
    
    page_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>Telegram RSS Feeds</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
            color: #2c3e50;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 30px;
            color: white;
            text-align: center;
        }}
        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        .meta {{
            color: rgba(255, 255, 255, 0.9);
            font-size: 13px;
            font-weight: 500;
            opacity: 0.95;
        }}
        .content {{
            padding: 40px 30px;
        }}
        h2 {{
            color: #2c3e50;
            font-size: 1.3em;
            margin-bottom: 25px;
            font-weight: 600;
            display: flex;
            align-items: center;
        }}
        .badge {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            margin-left: 10px;
            font-weight: 600;
        }}
        ul {{
            list-style: none;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 16px;
        }}
        li {{
            padding: 18px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
        }}
        li:hover {{
            border-color: #667eea;
            background: #f0f4ff;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
        }}
        a {{
            color: #667eea;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95em;
            transition: color 0.2s ease;
        }}
        a:hover {{
            color: #764ba2;
        }}
        li::before {{
            content: "✦";
            margin-right: 12px;
            color: #667eea;
            font-size: 1.1em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>RSS Feeds</h1>
            <div class="meta">
                <strong>Last update:</strong> {timestamp_str}
            </div>
        </div>
        
        <div class="content">
            <h2>
                Available Feeds
                <span class="badge">{len(registry['channels'])} channels</span>
            </h2>
            <ul>
{entries_markup}            </ul>
        </div>
    </div>
</body>
</html>
"""
    
    os.makedirs(destination_dir, exist_ok=True)
    
    output_path = os.path.join(destination_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as html_file:
        html_file.write(page_html)
    
    print(f"✓ index.html generated")
    print(f"✓ Channels added: {len(registry['channels'])}")
    print(f"✓ Time of update: {timestamp_str}")
    for entry in registry['channels']:
        print(f"  - {entry['title']} ({entry['name']}.xml)")


if __name__ == '__main__':
    build_html_page()
