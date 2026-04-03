import os
import markdown
import codecs
from flask import Flask, render_template, abort

app = Flask(__name__)
CONTENT_DIR = os.path.join(os.path.dirname(__name__), 'content')

def get_markdown_files():
    files = []
    if not os.path.exists(CONTENT_DIR):
        return files
    
    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith('.md'):
            # Read the file to get frontmatter metadata
            filepath = os.path.join(CONTENT_DIR, filename)
            with codecs.open(filepath, mode="r", encoding="utf-8") as f:
                text = f.read()
            
            md = markdown.Markdown(extensions=['meta'])
            md.convert(text)
            
            meta = getattr(md, 'Meta', {})
            title = meta.get('title', [filename[:-3]])[0]
            date = meta.get('date', [''])[0]
            description = meta.get('description', [''])[0]
            
            files.append({
                'id': filename[:-3],
                'title': title,
                'date': date,
                'description': description
            })
    
    # Sort files by date descending (optional)
    return sorted(files, key=lambda x: x['date'], reverse=True)

@app.route('/')
def index():
    files = get_markdown_files()
    return render_template('index.html', files=files)

@app.route('/<post_id>')
def post(post_id):
    filepath = os.path.join(CONTENT_DIR, f"{post_id}.md")
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
    
    title = meta.get('title', [post_id])[0]
    date = meta.get('date', [''])[0]
    description = meta.get('description', [''])[0]
    
    return render_template('post.html', 
                           title=title, 
                           date=date, 
                           description=description, 
                           content=html_content)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
