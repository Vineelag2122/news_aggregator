from flask import Flask, render_template,  request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash 
import os
import requests
from bs4 import BeautifulSoup
import feedparser
import time
from urllib.parse import urljoin

app = Flask(__name__)

app.secret_key = os.urandom(24)


RSS_FEEDS = {
    'India': 'https://timesofindia.indiatimes.com/rssfeeds/4719161.cms',
    'World': 'https://www.bbc.com/news/world/rss.xml',
    'Entertainment': 'https://variety.com/feed/',
    'Sports': 'https://www.espn.com/espn/rss/sportscenter/feed',
    'Data': 'https://www.wired.com/feed/category/data/rss',
    'Health': 'https://www.npr.org/rss/rss.php?id=1007',
    'Opinion': 'https://www.theguardian.com/commentisfree/rss',
    'Science': 'https://feeds.npr.org/1006/rss.xml',
    'Business': 'https://feeds.bloomberg.com/markets/news.rss'
}
FALLBACK_RSS = 'https://feeds.reuters.com/reuters/topNews'

def fetch_articles(rss_url, genre, limit=6):
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return []

        articles = []
        for entry in feed.entries[:limit]:
            title = entry.get('title', 'No Title')
            link = entry.get('link', '#')
            summary = entry.get('summary', '')

            # Try getting image
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                for media in entry.media_content:
                    if 'url' in media:
                        image_url = media['url']
                        break
            elif hasattr(entry, 'links') and entry.links:
                for link_item in entry.links:
                    if link_item.get('rel') == 'enclosure' and link_item.get('type', '').startswith('image'):
                        image_url = link_item['href']
                        break

            # Fallback image
            if not image_url:
                image_url = url_for('static', filename='images/veggies.jpg')

            articles.append({
                'title': title,
                'link': link,
                'summary': BeautifulSoup(summary, 'html.parser').get_text() if summary else 'No summary available.',
                'image': image_url
            })

        return articles
    except Exception as e:
        print(f"Error fetching {genre} news: {e}")
        return []

@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in to view your favorite news.", "warning")
        return redirect(url_for('login'))

    # Get user's favorite genres
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT category FROM favourites WHERE user_id = ?', (user_id,))
        fav_genres = [row[0] for row in cursor.fetchall()]
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        flash("Error accessing favourites.", "danger")
        return render_template('index.html', articles={})

    if not fav_genres:
        flash("No favourites found. Please add some genres.", "info")
        return render_template('index.html', articles={})

    # Fetch news for each favorite genre
    articles_by_genre = {}
    for genre in fav_genres:
        rss_url = RSS_FEEDS.get(genre)
        if not rss_url:
            flash(f"No RSS feed configured for {genre}.", "warning")
            continue

        articles = fetch_articles(rss_url, genre)
        if not articles:
            flash(f"No articles available for {genre}. Using fallback feed.", "warning")
            articles = fetch_articles(FALLBACK_RSS, genre)  # Use fallback feed

        if articles:
            articles_by_genre[genre] = articles

    if not articles_by_genre:
        flash("No news available for your favorite genres.", "info")
        return render_template('index.html', articles={})

    return render_template('index.html', articles=articles_by_genre)

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'danger')
            return redirect(url_for('login'))
        
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                         (username, email, hashed_password))
            conn.commit()
            conn.close()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already taken. Try another one.', 'danger')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()  # Clear the session to log the user out
    flash('You have been logged out.', 'info')  # Show a flash message
    return redirect(url_for('login'))  # Redirect to login page

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/india')
def india_news():
    feed_url = "https://feeds.feedburner.com/ndtvnews-india-news"
    feed = feedparser.parse(feed_url)

    articles = []
    for entry in feed.entries[:10]:
        # Try to get image from <media:content> first
        img_url = None
        if 'media_content' in entry and len(entry.media_content) > 0:
            img_url = entry.media_content[0]['url']
        
        # If not found, try to get image from the summary HTML
        if not img_url and 'summary' in entry:
            soup = BeautifulSoup(entry.summary, 'html.parser')
            img_tag = soup.find('img')
            if img_tag and 'src' in img_tag.attrs:
                img_url = img_tag['src']

        # Fallback image
        if not img_url:
            img_url = url_for('static', filename='images/veggies.jpg')

        # Clean summary text
        summary_text = BeautifulSoup(entry.summary, 'html.parser').get_text()

        articles.append({
            'title': entry.title,
            'link': entry.link,
            'summary': summary_text,
            'image': img_url
        })

    return render_template('india.html', articles=articles)

@app.route('/world')
def world_news():
    feed_url = "https://feeds.feedburner.com/ndtvnews-world-news"
    feed = feedparser.parse(feed_url)

    articles = []
    for entry in feed.entries[:10]:
        # Try to get image from <media:content> first
        img_url = None
        if 'media_content' in entry and len(entry.media_content) > 0:
            img_url = entry.media_content[0]['url']
        
        # If not found, try to get image from the summary HTML
        if not img_url and 'summary' in entry:
            soup = BeautifulSoup(entry.summary, 'html.parser')
            img_tag = soup.find('img')
            if img_tag and 'src' in img_tag.attrs:
                img_url = img_tag['src']

        # Fallback image
        if not img_url:
            img_url = url_for('static', filename='images/veggies.jpg')

        # Clean summary text
        summary_text = BeautifulSoup(entry.summary, 'html.parser').get_text()

        articles.append({
            'title': entry.title,
            'link': entry.link,
            'summary': summary_text,
            'image': img_url
        })

    return render_template('world.html', articles=articles)


@app.route('/entertainment')
def entertainment_news():
    try:
        api_key = "1ba1414923c547d9989cfb169e40a5df"  
        url = f"https://newsapi.org/v2/everything?q=movies+film+entertainment&apiKey={api_key}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        articles = []

        for article in data['articles'][:12]:
            image_url = article.get('urlToImage') or url_for('static', filename='images/veggies.jpg')
            articles.append({
                'title': article['title'],
                'link': article['url'],
                'summary': article.get('description', ''),
                'image': image_url
            })

        return render_template('entertainment.html', articles=articles)
    except Exception as e:
        print(f"Error fetching news: {str(e)}")
        flash(f'Error fetching news: {str(e)}', 'danger')
        return render_template('entertainment.html', articles=[])

@app.route('/sports')
def sports_news():
    try:
        feed_url = "https://feeds.feedburner.com/ndtvsports-latest"
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            flash('No articles found.', 'warning')
            return render_template('sports.html', articles=[])

        articles = []
        for entry in feed.entries[:10]:
            img_url = None
            if 'media_content' in entry and len(entry.media_content) > 0:
                img_url = entry.media_content[0]['url']
            
            if not img_url and 'summary' in entry:
                soup = BeautifulSoup(entry.summary, 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    img_url = img_tag['src']
                    if not img_url.startswith(('http://', 'https://')):
                        img_url = urljoin(entry.link, img_url)

            if not img_url:
                img_url = url_for('static', filename='images/veggies.jpg')

            summary_text = BeautifulSoup(entry.summary, 'html.parser').get_text()

            articles.append({
                'title': entry.title,
                'link': entry.link,
                'summary': summary_text,
                'image': img_url
            })

        return render_template('sports.html', articles=articles)
    except Exception as e:
        print(f"Error in sports_news: {str(e)}")
        flash(f'Error fetching news: {str(e)}', 'danger')
        return render_template('sports.html', articles=[])
    
@app.route('/data')
def data_news():
    try:
        feed_url = "https://techcrunch.com/category/artificial-intelligence/feed/"
        feed = feedparser.parse(feed_url)
        articles = []

        if not feed.entries:
            flash('No articles found.', 'warning')
            return render_template('data.html', articles=[])

        # Set up a requests session for webpage scraping
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

        for entry in feed.entries[:10]:
            title = entry.title
            link = entry.link
            summary = entry.summary if 'summary' in entry else entry.get('description', entry.get('content', [{}])[0].get('value', ''))

            img_url = None

            # Debugging
            print(f"Processing entry: {title}")
            print(f"Link: {link}")
            print(f"Summary: {summary[:100]}...")

            # Step 1: Check RSS feed for images
            if 'media_content' in entry and len(entry.media_content) > 0:
                img_url = entry.media_content[0]['url']
                print(f"Found media:content: {img_url}")
            elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
                img_url = entry.media_thumbnail[0]['url']
                print(f"Found media:thumbnail: {img_url}")
            elif 'content' in entry and len(entry.content) > 0:
                soup = BeautifulSoup(entry.content[0].value, 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    img_url = img_tag['src']
                    print(f"Found <img> in content: {img_url}")
            elif 'summary' in entry:
                soup = BeautifulSoup(entry.summary, 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    img_url = img_tag['src']
                    print(f"Found <img> in summary: {img_url}")
            else:
                print("No image fields found in RSS")

            # Resolve relative URLs
            if img_url and not img_url.startswith(('http://', 'https://')):
                img_url = urljoin(link, img_url)
                print(f"Resolved relative URL: {img_url}")

            # Step 2: Validate image URL
            if img_url:
                try:
                    response = session.head(img_url, timeout=3)
                    content_type = response.headers.get('content-type', '').lower()
                    if response.status_code == 200 and 'image' in content_type:
                        print(f"Valid image: {img_url}")
                    else:
                        print(f"Invalid image (status: {response.status_code}, content-type: {content_type})")
                        img_url = None
                except requests.RequestException as e:
                    print(f"Failed to validate image {img_url}: {str(e)}")
                    img_url = None

            # Step 3: Scrape webpage if no valid image
            if not img_url:
                try:
                    response = session.get(link, timeout=5)
                    response.raise_for_status()
                    page_soup = BeautifulSoup(response.text, 'html.parser')

                    # Try og:image
                    og_image = page_soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        candidate_url = og_image['content']
                        try:
                            img_response = session.head(candidate_url, timeout=3)
                            content_type = img_response.headers.get('content-type', '').lower()
                            if img_response.status_code == 200 and 'image' in content_type:
                                img_url = candidate_url
                                print(f"Valid og:image: {img_url}")
                            else:
                                print(f"Invalid og:image (status: {img_response.status_code}, content-type: {content_type})")
                        except requests.RequestException as e:
                            print(f"Failed to validate og:image {candidate_url}: {str(e)}")

                    # Try first <img> tag
                    if not img_url:
                        img_tag = page_soup.find('img', src=True)
                        if img_tag and img_tag.get('src'):
                            img_url = img_tag['src']
                            if not img_url.startswith(('http://', 'https://')):
                                img_url = urljoin(link, img_url)
                            try:
                                img_response = session.head(img_url, timeout=3)
                                content_type = img_response.headers.get('content-type', '').lower()
                                if img_response.status_code == 200 and 'image' in content_type:
                                    print(f"Valid webpage <img>: {img_url}")
                                else:
                                    print(f"Invalid webpage <img> (status: {img_response.status_code}, content-type: {content_type})")
                                    img_url = None
                            except requests.RequestException as e:
                                print(f"Failed to validate webpage <img> {img_url}: {str(e)}")
                                img_url = None
                        else:
                            print("No <img> tags found on webpage")
                except requests.RequestException as e:
                    print(f"Failed to fetch webpage {link}: {str(e)}")

            # Step 4: Fallback
            if not img_url:
                img_url = url_for('static', filename='images/veggies.jpg')
                print(f"Using fallback: {img_url}")

            # Clean summary text
            summary_text = BeautifulSoup(summary, 'html.parser').get_text()

            articles.append({
                'title': title,
                'link': link,
                'summary': summary_text,
                'image': img_url
            })

        session.close()
        return render_template('data.html', articles=articles)

    except Exception as e:
        print(f"Error in data_news: {str(e)}")
        flash(f'Error fetching news: {str(e)}', 'danger')
        return render_template('data.html', articles=[])

@app.route('/health')
def health_news():
    try:
        feed_url = "https://www.thehindu.com/sci-tech/health/feeder/default.rss"
        feed = feedparser.parse(feed_url)

        articles = []
        for entry in feed.entries[:10]:
            # Debugging
            print(f"Processing health article: {entry.title}")
            print(f"Link: {entry.link}")

            # Try to get image from <media:content> first
            img_url = None
            if 'media_content' in entry and len(entry.media_content) > 0:
                img_url = entry.media_content[0]['url']
                print(f"Found media:content: {img_url}")
            
            # If not found, try to get image from the summary HTML
            if not img_url and 'summary' in entry:
                soup = BeautifulSoup(entry.summary, 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    img_url = img_tag['src']
                    # Handle relative URLs
                    if not img_url.startswith(('http://', 'https://')):
                        img_url = urljoin(entry.link, img_url)
                    print(f"Found <img> in summary: {img_url}")

            # Validate image
            if img_url:
                try:
                    response = requests.head(img_url, timeout=3)
                    content_type = response.headers.get('content-type', '').lower()
                    if response.status_code != 200 or 'image' not in content_type:
                        print(f"Invalid image (status: {response.status_code}, content-type: {content_type})")
                        img_url = None
                except requests.RequestException as e:
                    print(f"Failed to validate image {img_url}: {str(e)}")
                    img_url = None

            # Fallback image
            if not img_url:
                img_url = url_for('static', filename='images/veggies.jpg')
                print(f"Using fallback: {img_url}")

            # Clean summary text
            summary_text = BeautifulSoup(entry.summary, 'html.parser').get_text() if 'summary' in entry else ''
            print(f"Summary: {summary_text[:100]}...")

            articles.append({
                'title': entry.title,
                'link': entry.link,
                'summary': summary_text,
                'image': img_url
            })

        if not articles:
            print("No health articles found in feed")
            flash('No health articles found.', 'warning')
            return render_template('health.html', articles=[])

        return render_template('health.html', articles=articles)

    except Exception as e:
        print(f"Error in health_news: {str(e)}")
        flash(f'Error fetching health articles: {str(e)}', 'danger')
        return render_template('health.html', articles=[])

@app.route('/opinion')
def opinion_news():
    try:
        rss_url = "https://www.thehindu.com/opinion/feeder/default.rss"
        feed = feedparser.parse(rss_url)

        if not feed.entries:
            print("No entries found in the feed")
            return render_template('opinion.html', articles=[])

        articles = []
        for entry in feed.entries[:12]:
            title = entry.title
            link = entry.link
            
            # Get summary from content or description
            summary = ''
            if 'content' in entry and entry.content:
                summary = BeautifulSoup(entry.content[0].value, 'html.parser').get_text()[:200] + '...'
            elif 'description' in entry:
                summary = BeautifulSoup(entry.description, 'html.parser').get_text()[:200] + '...'

            # Get image from content or media
            image_url = None
            if 'content' in entry and entry.content:
                soup = BeautifulSoup(entry.content[0].value, 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    image_url = img_tag['src']
            
            if not image_url and 'media_content' in entry and entry.media_content:
                image_url = entry.media_content[0]['url']

            if not image_url:
                image_url = url_for('static', filename='images/default_news.jpg')

            articles.append({
                'title': title,
                'link': link,
                'summary': summary,
                'image': image_url
            })

        return render_template('opinion.html', articles=articles)

    except Exception as e:
        print(f"Error fetching opinion news: {e}")
        flash("Failed to load opinion articles.", "danger")
        return render_template('opinion.html', articles=[])

@app.route('/science')
def science_news():
    articles = []
    try:
        # Using The Hindu's science feed
        rss_url = "https://www.thehindu.com/sci-tech/science/feeder/default.rss"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        feed = feedparser.parse(response.content)
        
        if not feed.entries:
            raise Exception("No entries found in the feed")

        for entry in feed.entries[:12]:  # Limit to 12 articles
            title = entry.title
            link = entry.link
            
            # Get summary, handle cases where it might not exist
            summary = ""
            if hasattr(entry, 'summary'):
                soup = BeautifulSoup(entry.summary, 'html.parser')
                summary = soup.get_text().strip()
            elif hasattr(entry, 'description'):
                soup = BeautifulSoup(entry.description, 'html.parser')
                summary = soup.get_text().strip()

            # Get image URL from media content or summary
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                image_url = entry.media_content[0]['url']
            else:
                # Try to find image in summary
                soup = BeautifulSoup(entry.summary if hasattr(entry, 'summary') else '', 'html.parser')
                img_tag = soup.find('img')
                if img_tag and 'src' in img_tag.attrs:
                    image_url = img_tag['src']
                    if not image_url.startswith(('http://', 'https://')):
                        image_url = urljoin(link, image_url)

            if not image_url:
                image_url = url_for('static', filename='images/default_news.jpg')

            articles.append({
                'title': title,
                'link': link,
                'summary': summary[:200] + '...' if summary else '',  # Truncate long summaries
                'image': image_url
            })

    except requests.RequestException as e:
        print(f"Network error fetching science news: {e}")
        flash("Unable to connect to news source. Please try again later.", "danger")
    except Exception as e:
        print(f"Error processing science news: {e}")
        flash("Failed to load science articles. Please try again later.", "danger")
    
    return render_template('science.html', articles=articles)

@app.route('/business')
def business_news():
    try:
        rss_url = "https://feeds.bloomberg.com/markets/news.rss"
        feed = feedparser.parse(rss_url)

        if not feed.entries:
            flash("No business articles available at the moment.", "warning")
            return render_template('business.html', articles=[])

        articles = []
        for entry in feed.entries[:12]:
            title = entry.get('title', 'No Title')
            link = entry.get('link', '#')
            summary = entry.get('summary', '')

            # Try getting image from media:content or enclosure
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                for media in entry.media_content:
                    if 'url' in media:
                        image_url = media['url']
                        break
            elif hasattr(entry, 'links') and entry.links:
                for link_item in entry.links:
                    if link_item.get('rel') == 'enclosure' and link_item.get('type', '').startswith('image'):
                        image_url = link_item['href']
                        break

            # Validate image
            if image_url:
                try:
                    res = requests.head(image_url, timeout=3)
                    if res.status_code != 200 or 'image' not in res.headers.get('content-type', ''):
                        image_url = None
                except requests.RequestException:
                    image_url = None

            # Fallback to default image
            if not image_url:
                image_url = url_for('static', filename='images/veggies.jpg')

            articles.append({
                'title': title,
                'link': link,
                'summary': BeautifulSoup(summary, 'html.parser').get_text() if summary else 'No summary available.',
                'image': image_url
            })

        return render_template('business.html', articles=articles)

    except Exception as e:
        print(f"Error fetching business news: {e}")
        flash("Failed to load business articles.", "danger")
        return render_template('business.html', articles=[])

@app.route('/favourites', methods=['GET', 'POST'])
def favourites():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in to manage your favourites.")
        return redirect(url_for('login'))

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        genre = request.form.get('genre')
        if genre:
            try:
                cursor.execute('INSERT INTO favourites (user_id, category) VALUES (?, ?)', (user_id, genre))
                conn.commit()
                flash("Genre added to your favourites!", "success")
            except sqlite3.IntegrityError:
                flash("Error adding genre.", "danger")
        else:
            flash("Please select a genre.", "warning")

    cursor.execute('SELECT category FROM favourites WHERE user_id = ?', (user_id,))
    fav_items = cursor.fetchall()
    conn.close()
    return render_template("favourites.html", fav_items=fav_items)

if __name__=="__main__":
    app.run(debug=True)