import os
import markdown
import codecs
import time
import re
from flask import Flask, render_template, abort, send_from_directory

app = Flask(__name__)
# Get absolute path to the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(BASE_DIR, 'content')
# Map report paths to local filesystem paths
CHART_BASE_DIR = os.path.join(BASE_DIR, 'charts')

def get_post_metadata(filepath):
    """Extract metadata and creation time from a markdown file."""
    try:
        # Get creation time (st_ctime or st_birthtime on some systems)
        stat = os.stat(filepath)
        ctime = getattr(stat, 'st_birthtime', stat.st_ctime)
        # Format as string for the UI
        date_str = time.strftime('%Y-%m-%d', time.localtime(ctime))
        
        with codecs.open(filepath, mode="r", encoding="utf-8") as f:
            text = f.read()
        
        md = markdown.Markdown(extensions=['meta'])
        md.convert(text)
        meta = getattr(md, 'Meta', {})
        
        # Prefer frontmatter date if available
        if 'date' in meta:
            date_str = meta['date'][0]

        return {
            'title': meta.get('title', [os.path.basename(filepath)[:-3]])[0],
            'date': date_str,
            'ctime': ctime, # Numeric timestamp for accurate sorting
            'description': meta.get('description', [''])[0]
        }
    except Exception:
        return None

def get_latest_ctime_in_dir(dir_path):
    """Recursively find the newest creation timestamp in all markdown files within a directory."""
    latest_ctime = 0.0
    for root, _, filenames in os.walk(dir_path):
        for filename in filenames:
            if filename.endswith('.md'):
                filepath = os.path.join(root, filename)
                try:
                    stat = os.stat(filepath)
                    ctime = getattr(stat, 'st_birthtime', stat.st_ctime)
                    if ctime > latest_ctime:
                        latest_ctime = ctime
                except Exception:
                    continue
    return latest_ctime

def get_content_items(rel_dir=""):
    """List items in a specific directory (non-recursive listing)."""
    target_path = os.path.join(CONTENT_DIR, rel_dir.strip('/'))
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        return []

    items = []
    # List current directory entries
    for entry in os.listdir(target_path):
        if entry.startswith('.'):
            continue
            
        full_path = os.path.join(target_path, entry)
        rel_item_path = os.path.join(rel_dir, entry).replace(os.sep, '/').strip('/')
        
        if os.path.isdir(full_path):
            # It's a folder: get latest creation time inside
            latest_ctime = get_latest_ctime_in_dir(full_path)
            items.append({
                'id': rel_item_path,
                'title': entry,
                'type': 'folder',
                'date': time.strftime('%Y-%m-%d', time.localtime(latest_ctime)) if latest_ctime > 0 else '',
                'ctime': latest_ctime,
                'description': f"Collection of documents in {entry}"
            })
        elif entry.endswith('.md'):
            # It's a file
            meta = get_post_metadata(full_path)
            if meta:
                items.append({
                    'id': rel_item_path[:-3], # remove .md
                    'title': meta['title'],
                    'type': 'file',
                    'date': meta['date'],
                    'ctime': meta['ctime'],
                    'description': meta['description']
                })

    # Sort: Folders first (is_folder=1), then creation time descending
    def sort_key(item):
        is_folder = (1 if item['type'] == 'folder' else 0)
        return (is_folder, item['ctime'], item['title'])

    return sorted(items, key=sort_key, reverse=True)

def get_fuzzy_file_match(req_path):
    """Find the most recently created markdown file that fuzzy matches the requested path."""
    best_match = None
    max_ctime = -1
    
    query = req_path.lower().split('/')[-1].strip('/')
    base_dir = os.path.join(CONTENT_DIR, '/'.join(req_path.split('/')[:-1]))
    for filename in os.listdir(base_dir):
        if filename.endswith('.md'):
            full_path = os.path.join(base_dir, filename)
            # Get only the filename without extension
            filename_only = os.path.basename(full_path)[:-3].lower()
                
            # Check if the query is in the filename (fuzzy matching)
            if query in filename_only:
                try:
                    stat = os.stat(full_path)
                    ctime = getattr(stat, 'st_birthtime', stat.st_ctime)
                    if ctime > max_ctime:
                        max_ctime = ctime
                        best_match = full_path
                except Exception:
                    continue
    return best_match

def preprocess_markdown(text):
    """Pre-process markdown text to handle custom tags and formatting issues."""
    
    # 1. Handle <<CHART_UPLOAD:path>> tags before markdown conversion
    # This avoids escaping issues where << becomes &lt;<
    def replace_chart_tag(match):
        content = match.group(1).strip()
        # If it has an image extension, treat as an image path/filename
        if any(content.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            filename = os.path.basename(content)
            return f'<div class="chart-container"><img src="/charts/{filename}" alt="Chart: {filename}" class="chart-image"></div>'
        else:
            # Treat as an error or status message
            return f'<div class="chart-error">📊 {content}</div>'
    
    text = re.sub(r'<<CHART_UPLOAD:(.*?)>>', replace_chart_tag, text)

    # 2. Fix common issues with Python-Markdown:
    # - Ensure a blank line exists before any list block (Python-Markdown requirements)
    # - Normalize 2-space indentation to 4-space for nested list items.
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        is_list_item = bool(re.match(r'^(\s*)([-*+]|\d+\.)\s', line))
        if is_list_item:
            # Normalize 2-space indentation to 4-space for nested items
            indent_match = re.match(r'^( +)', line)
            if indent_match:
                spaces = indent_match.group(1)
                # Double the indent: 2->4, 4->8, etc.
                line = (' ' * len(spaces)) + line

            # Ensure blank line before the start of a list block
            if i > 0:
                prev_line = lines[i - 1].strip()
                prev_is_list = bool(re.match(r'^(\s*)([-*+]|\d+\.)\s', lines[i - 1]))
                # If previous line is not blank, not a list item, and not a heading
                if prev_line and not prev_is_list and not prev_line.startswith('#'):
                    result.append('')
        result.append(line)
    
    text = '\n'.join(result)
    
    # 3. Strip wrapping markdown code blocks if the entire content is wrapped
    text = text.strip()
    if text.startswith('```markdown') and text.endswith('```'):
        text = text[11:-3].strip()
    elif text.startswith('```') and text.endswith('```'):
        text = text[3:-3].strip()
        
    return text

@app.route('/charts/<path:filename>')
def serve_chart(filename):
    """Serve chart images from the local charts directory."""
    if not os.path.exists(CHART_BASE_DIR):
        abort(404)
    return send_from_directory(CHART_BASE_DIR, filename)

@app.route('/')
def index():
    items = get_content_items("")
    return render_template('index.html', files=items, current_path="")

@app.route('/<path:req_path>')
def catch_all(req_path):
    # Explicitly exclude charts directory from document matching
    if req_path.startswith('charts/'):
        abort(404)
        
    # Check if it's a directory
    dir_path = os.path.join(CONTENT_DIR, req_path)
    if os.path.isdir(dir_path):
        items = get_content_items(req_path)
        return render_template('index.html', files=items, current_path=req_path)
    
    # Check if it's a markdown file
    filepath = os.path.join(CONTENT_DIR, f"{req_path}.md")
    if not os.path.exists(filepath):
        # Fuzzy match fallback
        fuzzy_path = get_fuzzy_file_match(req_path)
        if fuzzy_path:
            filepath = fuzzy_path
        else:
            abort(404)
        
    with codecs.open(filepath, mode="r", encoding="utf-8") as f:
        text = f.read()

    # Pre-process markdown text
    text = preprocess_markdown(text)
        
    md = markdown.Markdown(extensions=[
        'meta', 
        'fenced_code', 
        'extra',
        'codehilite',
        'sane_lists'
    ])
    html_content = md.convert(text)
    
    meta = getattr(md, 'Meta', {})
    title = meta.get('title', [req_path.split('/')[-1]])[0]
    date = meta.get('date', [''])[0]
    description = meta.get('description', [''])[0]
    
    return render_template('post.html', 
                           title=title, 
                           date=date, 
                           description=description, 
                           content=html_content)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
