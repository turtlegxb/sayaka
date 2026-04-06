import os
import markdown
import codecs
import time
from flask import Flask, render_template, abort

app = Flask(__name__)
# Get absolute path to the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(BASE_DIR, 'content')

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

@app.route('/')
def index():
    items = get_content_items("")
    return render_template('index.html', files=items, current_path="")

@app.route('/<path:req_path>')
def catch_all(req_path):
    # Check if it's a directory
    dir_path = os.path.join(CONTENT_DIR, req_path)
    if os.path.isdir(dir_path):
        items = get_content_items(req_path)
        return render_template('index.html', files=items, current_path=req_path)
    
    # Check if it's a markdown file
    filepath = os.path.join(CONTENT_DIR, f"{req_path}.md")
    if not os.path.exists(filepath):
        abort(404)
        
    with codecs.open(filepath, mode="r", encoding="utf-8") as f:
        text = f.read()
        
    md = markdown.Markdown(extensions=[
        'meta', 
        'fenced_code', 
        'tables', 
        'codehilite'
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

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
