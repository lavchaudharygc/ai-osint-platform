Section 1:----      Telegram Osint Bots (Publicly Available)  ---------------------------------------------------------------

                 These are Telegram bots that provide intelligence. Access them by searching their username in Telegram.
                 
    Bot 1:---   @userinfobot
          - Status:---     Active & Free
          - Features:---
                         - Telegram User ID from username
                         - First seen date
                         - Account creation estimation
                         - Usage: Send username → Get ID + dates
                         - API Available: No (manual or screen scraping only) 
                         - Alternative: Direct API call to Telegram servers
                         
    Bot 2:---   @SangMataInfo_bot
         - Status:---     Partially Active (may be rate-limited)
         - Features:---   
                         - Previous usernames history
                         - Name change history
                         - Profile photo change tracking 
                         - Usage: Send username → Get username/name history
                         - API Available: No
                         - Alternative: Wayback Machine for historical t.me pages

    Bot 3:---   @tgdb_search_bot
        - Status:---    Active
        - Features:---  
                        - Group/channel lookup
                        - Public group join dates
                        - Message count estimation
                        - Usage: Send username → Get group list
                        - API Available: No
                        - Alternative: TelegramDB.org web interface

    Bot 4:---    @getidsbot
         - Status:---    Active
         - Features:---    
                        - User ID from username
                        - Chat ID from group/channel
                        - Forward message to get IDs
                        - Usage: Forward message or send username
                        - API Available: No
                        - Alternative: Direct MTProto API
                        
    Bot 5:---   @combot
         - Status:---    Active
         - Features:---
                        - Group management stats
                        - User activity tracking
                        - Spam detection
                        - Member join/leave history
                        - Usage: Add bot to group → Get analytics
                        - API Available: No
                        - Alternative: Custom group analytics

    Bot 6:---   @telesintseet_bot
         - Status:---   Active
         - Features:--- 
                        - Comprehensive profile analysis
                        - Group membership mapping
                        - Activity timeline generation
                        - Api Available: No
                        
    Bot 7:---   @Tginfosisbot
         - Status:---   Active
         - Features:--- 
                       - Detailed Id/User Data Extractioin
                       - Chat Type Detection
                       - User joined Group detection
                       - Groups Analysis
                       - Channel Analysis
                       - Usage: Just Send User id
                       - Api Available: NO
                       - Friends Analysis
                       - Reactions in group
                       - Api available: No
                       
    Bot 8:---   @en_SearchBot
         - Status:---   Active
         - Features:---
                       - Find Any Channel or group on Telegram
                       - Find Any Bot & Post
                       - Usage: Send Keyword to Search
                       - Api Available: No
                       
    Bot 9:---   @Funstatfan13_bot              
          - Status:---   Active
          - Features:--- 
                       - Profile Analysis
                       - Search for interest and likes
                       - Activity in groups
                       - History of Name Changes
                       - Monitoring of all telegram
                       - Search by groups
                       - Search by users by names
 
    Bot 10:---    @usercrawlerbot
          - Status:---  Acctive
          - Features:---
                        - Profile Analysis
                        - Language
                        - Status
                        - Gift
                        - Registerd
                        - Update / Found
                        - Group / Chanels
                        - Profile Changes
                        - Available Groups
                        - total Messages
                       
                       
                       
                       
                       
INTELLIGENCE/LEAKED Based Bots         ---------------------------------------------------------------------------------------------
                       
                       
    Bot 1:---  @EgorLeaks_bot
    
         - Type:--- Credential breach checker
         - Features:--- 
                       - Checks emails/usernames against 15+ billion compromised credentials
                       - Returns immediate breach results
                       - Status: Active, widely used 
                       - Caution: Entering sensitive information carries inherent risk
         - Paid 
         - Status:---  - Active  
               
               
    Bot 2:---   @Breach_Forums_Bot
         - Type:---  Credential breach checker
         - Features:---
                       - Search by Email
                       - Search by Nickname
                       - Search by phonenumber
                       - Search by Password
                       - Search by Car
                       - Search by Social Media Accounts
        - Paid
        - Status:---   - Active 
        
        
        
    Bot 3:---   @Vehicleinforobot
          - Type:---   Vehicle INformation
          - Features:---
                       - Search by Vehicle Number
                       - Find Rc
                       - Check Challan
                       - Vehicle number to Phone number 
         - Paid
         - Status:---  -Active 
         
         
         
    Bot 4:---   @Th3Darkn1ghtR1s3s_bot
         - Type:---   Telegram ID to Details
         - Features:---
                      - Get Phone NUmber from Tg User id
                      - Search by Social media Username
                      - Search by Contact
                      - Search by Documents
                      - Online Traces
        - paid
        - Status:---  - Active 
        
        
        
    Bot 5:---   @osintversebot
        - Features:--- 
                     - Vehicle Info
                     - Phone number info
        - Paid
        - Status:---  - Active
    
    
    
    Bot 6:---  @numberdetail4bot
         - Features:--- 
                     - Number Details Bot
                     - aadhar number
                     - address
                     - fater name
         - Paid
         - Status:---  - Active
                    
                    
                    
    Bot 7:---   @TrueCalleRobot
         - Features:---
                      - Number Name
                      - Unknows Says
                      - Sometime Shows Email too (if Available)
                      - Sometime shows Facebook Profile And Another Social Media Account too (if Available)
                      - Whatsapp And Telegram Link (if Available)
                      - Carrier
                      - Location
         - free
         - Status:---   - Active
         
         
         
    Bot 8:---   @josusbekbot
        - Features:---  
                     - Find Number Linked By telegram
        - Paid/free
        - Status:---  - Active
        
        
        
    Bot 9:---    @LeakCheck1_bot
        - Features:---
                     - Leak check by any email
                     - Get details of leaks
        - paid:---    - full details
        - free:---    - only leak sites/domain name
        - Status:---   - Active
    
    
    
Section 2:----   Public Data Sources ( no Api/Bot )  ------------------------------------------------------------------

               METHOD 1:---  URL Pattern: https://t.me/{username}
               Data Available:---

                                  - Display name (if set)
                                  - Profile photo (if public)
                                  - Bio/Description
                                  - "Last seen" status (if not hidden)
                                 
               Limitation:---     No Histroical Data/ No private Info
               
               Implementation:---   Web scarping

```python
import requests
from bs4 import BeautifulSoup

def scrape_profile(username):
    url = f"https://t.me/{username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    title = soup.find('meta', property='og:title')
    description = soup.find('meta', property='og:description')
    image = soup.find('meta', property='og:image')
    
    return {
        'name': title['content'] if title else None,
        'bio': description['content'] if description else None,
        'photo': image['content'] if image else None
    }





               METHOD 2:---   URL Pattern:  https://t.me/s/{channel_name}
               Data Available:---
               
                                 - All public channel messages
                                 - Media attachments (preview)
                                 - Message timestamps
                                 - Engagement (views, forwards)
                                 - Channel description
                                 - Subscriber count (if visible)
                                 
                Limitation:---  Only Public Channel , Limited history
                
                Implementation:---   Web Scarping
    
import requests
from bs4 import BeautifulSoup

def scrape_channel(channel_name):
    url = f"https://t.me/s/{channel_name}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    messages = []
    for msg in soup.find_all('div', class_='tgme_widget_message')[:20]:
        text = msg.find('div', class_='tgme_widget_message_text')
        date = msg.find('time')
        
        messages.append({
            'text': text.text if text else None,
            'date': date['datetime'] if date else None
        })
    
    return messages    
    
     
     
     
                METHOD 3:---   Google Dorking For Telegram
                URL Pattern:---   https://www.google.com/search?q=%7Bdork_query%7D
                Data Available:---
                                 - Any public mention of username
                                 - Links to groups/channels
                                 - Cross-platform references
                Dork Queries:----
                                  1. "{username}" site:t.me
                                  2. "@{username}" site:t.me
                                  3. "{username}" "telegram" "group"
                                  4. "{username}" "t.me" "joinchat"
                                  5. "{username}" telegram channel
                                  6. "t.me/{username}" 
                                  7. intitle:telegram "{username}"
                                  8. inurl:t.me "{username}"
                                  9. "{username}" "telegram" "contact"
                                  10. site:t.me "{username}" bio
                        
                 Implementation:---    SerpAPI or DuckDuckGo scraping
                 
import requests
from urllib.parse import quote

def google_dork(username):
    dorks = [
        f'"{username}" site:t.me',
        f'"@{username}" site:t.me'
    ]
    
    results = []
    for dork in dorks:
        query = quote(dork)
        # Using DuckDuckGo API (free)
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(url)
        data = response.json()
        results.extend(data.get('RelatedTopics', []))
    
    return results                 
    
    
    
    
                    METHOD 4:---   TGstat.com
                    URL pattern:---   URL: https://tgstat.com/search?q={username}
                    Data Available:---
                                    - Channel/Group subscriber count
                                    - Daily growth rate
                                    - Engagement metrics
                                    - Post views and forwards
                                    - Weekly/monthly statistics
                                    - Audience demographics
                                    - Mention tracking
                                    - Top channels by category
                                    - Similar channels recommendations
                                    - Activity patterns
                                     
                    Limitation:---   Focus on channels, limited user data
    
                    Implementation:----     Web scraping (requires JavaScript rendering)
    
import requests
from bs4 import BeautifulSoup
import re

def search_tgstat(username):
    url = f"https://tgstat.com/search?q={username}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    for item in soup.find_all('div', class_='search-item'):
        name = item.find('div', class_='search-item-title')
        stats = item.find('div', class_='search-item-stats')
        
        if name:
            link = name.find('a')
            results.append({
                'name': link.text if link else None,
                'url': link.get('href') if link else None,
                'subscribers': re.findall(r'\d+', stats.text)[0] if stats else '0'
            })
    
    return results
    
    
    
    
                 METHOD 5:---   Telemetr.io
                     URL Method:---   https://telemetr.io/en/channels?search={username}
                     Data Available:---
                                      - Channel/subscriber analytics
                                      - Engagement rate
                                      - Mention frequency
                                      - Category classification
                                      - Similar channels
                                      - Post reach metrics
                                      - Daily active users
                                      - Audience interests
                                      - Top influencers in category
                                      - Content performance analysis
                                      - Channel ranking
                                      - Historical growth data
                                      
                    Limitation:---   Requires registration for full access
                    
                    Implementation:----        API or web scraping
                    
import requests
from bs4 import BeautifulSoup

def search_telemetr(username):
    url = f"https://telemetr.io/en/channels?search={username}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    for channel in soup.find_all('div', class_='channel-item'):
        name = channel.find('div', class_='channel-name')
        subs = channel.find('div', class_='subscribers-count')
        
        results.append({
            'name': name.text if name else None,
            'subscribers': subs.text if subs else None,
            'url': channel.find('a').get('href') if channel.find('a') else None
        })
    
    return results




                     METHOD 6:---     Wayback Machine
                     URL pattern:--- https://web.archive.org/web/*/https://t.me/{username}
                     Data Available:---
                                       - Historical profile snapshots
                                       - Previous usernames (from old URLs)
                                       - Bio changes over time
                                       - Profile photo changes

                     Implementation: Web scraping
                     
import requests
from bs4 import BeautifulSoup

def wayback_check(username):
    url = f"https://web.archive.org/web/*/https://t.me/{username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    snapshots = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'web/' in href:
            snapshots.append({
                'url': f"https://web.archive.org{href}",
                'date': link.text.strip()
            })
    
    return snapshots[:10]                     
                     
                     
                     
                     
                     
                     METHOD 7:---      Google Cache
                     URL Pattern:--- https://webcache.googleusercontent.com/search?q=cache:t.me/{username}
                     Data Available:--- 
                                      - Last cached version of profile
                                      - Recent bio/name

                     Implementation: Web scraping

import requests
from bs4 import BeautifulSoup

def google_cache(username):
    url = f"https://webcache.googleusercontent.com/search?q=cache:t.me/{username}"
    response = requests.get(url)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('meta', property='og:title')
        desc = soup.find('meta', property='og:description')
        
        return {
            'name': title['content'] if title else None,
            'bio': desc['content'] if desc else None
        }
    return None





                     METHOD 8:---      DuckDuckGo Search
                     URL Pattern:---   https://api.duckduckgo.com/?q={username}+telegram&format=json
                     Data Available:---
                                      - Related topics
                                      - External links mentioning username
                                      - Telegram-related references

                     Implementation: API (free, no key required)
                     
import requests

def duckduckgo_search(username):
    url = f"https://api.duckduckgo.com/?q={username}+telegram&format=json"
    response = requests.get(url)
    data = response.json()
    
    return {
        'abstract': data.get('Abstract', ''),
        'related_topics': data.get('RelatedTopics', [])
    }
                     
                     
                    
                    
                    
                     METHOD 9:---      Email Harvesting
                     URL Pattern:---    https://t.me/{username} + Email pattern matching
                     Data Available:---
                                      - Email addresses in bio 
                                      - Contact information
                                      - Public contact details

                    Implementation: Web scraping + Regex 

import requests
from bs4 import BeautifulSoup
import re

def extract_emails(text):
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(pattern, text)

def extract_phones(text):
    pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    return re.findall(pattern, text)

def harvest_contacts(username):
    url = f"https://t.me/{username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    bio_elem = soup.find('meta', property='og:description')
    bio = bio_elem['content'] if bio_elem else ''
    
    return {
        'emails': extract_emails(bio),
        'phones': extract_phones(bio)
    }





                    METHOD 10:---      Pastebin Search
                    URL Pattern:--- https://pastebin.com/search?q={username}+telegram
                    Data Available:---
                                      - Pastes mentioning username
                                      - Source code snippets
                                      - Configuration files
                                      - Credential leaks
                                      
                    Implementation: Web scraping
                    
import requests
from bs4 import BeautifulSoup

def pastebin_search(username):
    url = f"https://pastebin.com/search?q={username}+telegram"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    for paste in soup.find_all('div', class_='paste'):
        title = paste.find('a')
        if title:
            results.append({
                'title': title.text,
                'url': f"https://pastebin.com{title.get('href')}"
            })
    
    return results

    
        
            
            
                    METHOD 11:---     URL Extraction
                    URL Pattern:---    Any scraped text data
                    Data Available:---
                                      - All URLs containing username
                                      - Links from various platforms

                    Implementation: Regex extraction 
                    
import re

def extract_telegram_urls(text):
    patterns = [
        r'https?://t\.me/[^\s]+',
        r'https?://telegram\.me/[^\s]+',
        r't\.me/[^\s]+',
        r'@[a-zA-Z0-9_]{5,32}'
    ]
    
    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        urls.extend(matches)
    
    return list(set(urls))
    
    
    
    
    
                    METHOD 12:---     Medium Search
                    URL Pattern:---   https://medium.com/search?q=%7Busername%7D+telegram
                    Data Available:---
                                    - Blog posts mentioning username
                                    - Articles referencing Telegram
                                    
                    Implementation:---   Web Scarping
                    
import requests
from bs4 import BeautifulSoup

def medium_search(username):
    url = f"https://medium.com/search?q={username}+telegram"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    for article in soup.find_all('div', class_='postArticle')[:10]:
        title = article.find('h3')
        link = article.find('a', class_='postArticle-title')
        
        if title and link:
            results.append({
                'title': title.text,
                'url': link.get('href')
            })
    
    return results
    
    
    
    
                    METHOD 13:---    File Type Search
                    URL Pattern:---   Search Engine Query
                    Data Available:---   
                                    - Documents containing username
                                    - PDF, DOC, TXT files with references
                                    
                    Implementation:---  DuckDuckGo API (free)
                    
import requests

def search_file_types(username):
    file_types = ['pdf', 'doc', 'txt', 'json']
    results = {}
    
    for ext in file_types:
        query = f'"{username}" filetype:{ext} telegram'
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(url)
        data = response.json()
        results[ext] = len(data.get('RelatedTopics', []))
    
    return results
    
    
    
    
    
                   METHOD 14:---    Github Search
                   URL PAttern:---   https://github.com/search?q=t.me%252F{username}
                   Data Available:--- 
                                   - Code files with username
                                   - README mentions
                                   - Config files with links
                                   
                  Implementation:---  GitHub API (no key required for public)
                  
import requests

def github_search(username):
    url = f"https://api.github.com/search/code?q=t.me/{username}"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return {
            'total_count': data['total_count'],
            'items': [{'path': item['path'], 'url': item['html_url']} 
                     for item in data.get('items', [])[:5]]
        }
    return None
    
    
    
    
    
    
SECTION 3:----     TELEGRAM MTProto API (Requires API Credentials)    -------------------------------------------------------

                       Setup Required:---
                                      - Go to https://my.telegram.org
                                      - Login with phone number
                                      - Create application → Get API_ID and API_HASH
                                      - Install Telethon library:
                                        ```bash
                                             pip install telethon
                                             
                                                
                METHOD 1:---   Get User Information
                    Type:---   API (MTProto)
                    Data Available:---
                                      - User ID (numeric)
                                      - Username
                                      - First name & Last name                                     
                                      - Phone number (if visible)
                                      - Profile photo
                                      - Online/offline status
                                      - Premium status
                                      - Bot/User detection
                                      
    Implementation:---   
                    
from telethon import TelegramClient

api_id = YOUR_API_ID
api_hash = 'YOUR_API_HASH'

client = TelegramClient('session', api_id, api_hash)
client.start()

async def get_user_info(username):
    user = await client.get_entity(username)
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone if hasattr(user, 'phone') else None,
        'premium': user.premium if hasattr(user, 'premium') else False,
        'verified': user.verified if hasattr(user, 'verified') else False,
        'bot': user.bot,
        'status': str(user.status) if hasattr(user, 'status') else None
    }




                 METHOD 2:---    Get Message History
                        Type:---  API (MTProto)
                        Data Available:--- 
                                         - All messages (if user is contact/member)
                                         - Message text
                                         - Media files
                                         - Timestamps 
                                         - Forwarded messages
                                         - Reactions

      Implementation:---
      
async def get_messages(username, limit=100):
    user = await client.get_entity(username)
    messages = await client.get_messages(user, limit=limit)
    
    return [{
        'text': msg.text,
        'date': str(msg.date),
        'has_media': bool(msg.media),
        'forwarded': bool(msg.forward)
    } for msg in messages]
    
    
    
    
                 METHOD 3:---     Get Common Groups
                        Type:---  API (MTProto)
                        Data Available:---
                                         - Groups where both users are members
                                         - Group names 
                                         - Group IDs
                                         
     Implementation:---
     
async def get_common_groups(username):
    target = await client.get_entity(username)
    common = await client.get_common_chats(target)
    
    return [{
        'id': chat.id,
        'title': chat.title,
        'participants': chat.participants_count if hasattr(chat, 'participants_count') else None
    } for chat in common]
    
    
    
    
                    METHOD 4:---    Get Group Participants
                           Type:--- API (MTProto)
                           Data Available:---
                                            - All group members 
                                            - Member IDs 
                                            - Usernames 
                                            - Online status
                                            
    Implementation:---
    
async def get_group_members(group_username):
    group = await client.get_entity(group_username)
    participants = await client.get_participants(group)
    
    return [{
        'id': p.id,
        'username': p.username,
        'first_name': p.first_name,
        'last_name': p.last_name,
        'online': p.status is not None
    } for p in participants]
    
    
    
    
                    METHOD 5:---     Get User Photos
                           Type:---   API (MTProto)
                           Data Available:--- 
                                             - Profile photos
                                             - Photo dates
                                             - Photo URLs
                                             
    Implementation:---
    
async def get_profile_photos(username):
    user = await client.get_entity(username)
    photos = await client.get_profile_photos(user)
    
    return [{
        'id': photo.id,
        'date': str(photo.date),
        'file_reference': photo.file_reference
    } for photo in photos]
    
    
    
    
                    METHOD 6:---     Get User Status
                           Type:---   API (MTProto)
                           Data Available:--- 
                                            - Online/offline status 
                                            - Last seen timestamp
                                            - Recent activity
                                            
    Implementation:---
    
async def get_user_status(username):
    user = await client.get_entity(username)
    
    return {
        'online': user.status,
        'last_seen': user.status.was_online if hasattr(user.status, 'was_online') else None,
        'is_online': user.status.is_online if hasattr(user.status, 'is_online') else False
    }
    
    
    
    
                     METHOD 7:---     Download Media
                            Type:---   API (MTProto)
                            Data Available:---
                                              - Images 
                                              - Videos
                                              - Documents 
                                              - Audio files
                                              
    Implementation:---
    
    async def download_media(username, limit=5):
    user = await client.get_entity(username)
    messages = await client.get_messages(user, limit=limit)
    
    media_files = []
    for msg in messages:
        if msg.media:
            path = await client.download_media(msg)
            media_files.append({
                'file_path': path,
                'date': str(msg.date)
            })
    
    return media_file
    
    
    
    
                     METHOD 8:---     Get Dialog List
                            Type:---   API (MTProto) 
                            Data Available:--- 
                                              - All chats/groups/channels user is part of
                                              - Dialog details
                                              - Unread counts
                                              
    Implementation:---
    
async def get_dialogs():
    dialogs = await client.get_dialogs()
    
    return [{
        'id': dialog.id,
        'name': dialog.name,
        'unread_count': dialog.unread_count,
        'is_group': dialog.is_group,
        'is_channel': dialog.is_channel
    } for dialog in dialogs]
    
    
    
    
                    METHOD 9:---      Send/Check Message
                           Type:---    API (MTProto)
                           Data Available:--- 
                                            - Send messages (if authorized) 
                                            - Message delivery status
                                            
     Implementation:---
     
     async def send_message(username, text):
    user = await client.get_entity(username)
    result = await client.send_message(user, text)
    
    return {
        'id': result.id,
        'date': str(result.date),
        'message': result.message
    }




                    METHOD 10:---      Get User Full Profile
                           Type:---    API (MTProto)  
                           Data Available:--- 
                                             - Complete profile data
                                             - Bio
                                             - Stats
                                             - About section
                                             
    Implementation:---

async def get_full_profile(username):
    user = await client.get_entity(username)
    full = await client.get_user(user)
    
    return {
        'id': full.user.id,
        'username': full.user.username,
        'first_name': full.user.first_name,
        'last_name': full.user.last_name,
        'bio': full.about,
        'phone': full.user.phone if hasattr(full.user, 'phone') else None
    }
    
    
    
    
                    METHOD 11:---     Search Messages
                           Type:---    API (MTProto)
                           Data Available:---
                                            - Messages with specific keyword 
                                            - Messages in specific chat
                                            
    Implementation:---
    
async def search_messages(username, keyword, limit=50):
    user = await client.get_entity(username)
    messages = await client.get_messages(user, search=keyword, limit=limit)
    
    return [{
        'text': msg.text,
        'date': str(msg.date),
        'matches': keyword in msg.text if msg.text else False
    } for msg in messages]
    
    
    
    
                             
                            METHOD 12:---    Get User Contacts
                                   Type:---   API (MTProto) 
                                   Data Available:---
                                                     - User's contact list 
                                                     - Contact details
                                                     - Mutual contacts
                                                
    Implementation:---
    
async def get_contacts():
    contacts = await client.get_contacts()
    
    return [{
        'id': c.id,
        'username': c.username,
        'first_name': c.first_name,
        'last_name': c.last_name,
        'phone': c.phone
    } for c in contacts]
    
    
    
    
    
                            METHOD 13:---     Check Username Availability
                                   Type:---    API (MTProto)
                                    Data Available:---  
                                                      - Whether username exists
                                                      - Account type (user/bot/group)

   Implementation:---
   
async def check_username(username):
    try:
        entity = await client.get_entity(username)
        return {
            'exists': True,
            'type': 'user' if entity.is_user else 'group' if entity.is_group else 'channel'
        }
    except:
        return {'exists': False}
        
        
        
        
        
                            METHOD 14:---     Get Channel Stats
                                   Type:---   API (MTProto)
                                   Data Available:---
                                                     - Channel info
                                                     - Member count 
                                                     - Admin list
                                                     
    Implementation:---
    
async def get_channel_info(channel_username):
    channel = await client.get_entity(channel_username)
    participants = await client.get_participants(channel)
    
    return {
        'id': channel.id,
        'title': channel.title,
        'username': channel.username,
        'member_count': len(participants) if participants else None,
        'is_public': channel.username is not None
    }
    
    
    
    
    COMPLETE API IMPLEMENTATION CLASS:-------------------------------------------
    
    from telethon import TelegramClient
from telethon.errors import FloodWaitError
import asyncio
import json

class TelegramAPIIntel:
    def __init__(self, api_id, api_hash):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = TelegramClient('session', api_id, api_hash)
    
    async def start(self):
        await self.client.start()
    
    async def get_user_info(self, username):
        user = await self.client.get_entity(username)
        return {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': user.phone if hasattr(user, 'phone') else None,
            'premium': user.premium if hasattr(user, 'premium') else False,
            'bot': user.bot,
            'status': str(user.status) if hasattr(user, 'status') else None
        }
    
    async def get_messages(self, username, limit=100):
        user = await self.client.get_entity(username)
        messages = await self.client.get_messages(user, limit=limit)
        return [{'text': msg.text, 'date': str(msg.date)} for msg in messages]
    
    async def get_common_groups(self, username):
        target = await self.client.get_entity(username)
        common = await self.client.get_common_chats(target)
        return [{'id': c.id, 'title': c.title} for c in common]
    
    async def close(self):
        await self.client.disconnect()

# Usage
async def main():
    intel = TelegramAPIIntel(api_id=123456, api_hash='your_hash')
    await intel.start()
    
    info = await intel.get_user_info('username')
    print(json.dumps(info, indent=2))
    
    await intel.close()

asyncio.run(main())





        API RATE LIMIT AAND ERROR HANDLING:-------------------------------------------
        
    from telethon.errors import FloodWaitError
import time

async def api_call_with_retry(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except FloodWaitError as e:
        print(f"Rate limited. Waiting {e.seconds} seconds...")
        await asyncio.sleep(e.seconds)
        return await func(*args, **kwargs)
    except Exception as e:
        return {'error': str(e)}
        
        
        
        
        
SECTION 4:----     ALTERNATIVE METHODS (If Bots/API Unavailable)  --------------------------------------------------------------

                   METHOD 1:---   Wayback Machine (Archive.org)
                   URL Pattern:---  https://web.archive.org/web/*/https://t.me/{username}
                   Data Available:---
                                     - Historical profile snapshots
                                     - Previous usernames (from old URLs)
                                     - Bio changes over time 
                                     - Profile photo changes
                                     - Deleted/renamed profiles history 
                  Limitation:---  Depends on crawl frequency
        
    Implementation:---  Web Scarping

import requests
from bs4 import BeautifulSoup

def wayback_check(username):
    url = f"https://web.archive.org/web/*/https://t.me/{username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    snapshots = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'web/' in href:
            snapshots.append({
                'url': f"https://web.archive.org{href}",
                'date': link.text.strip()
            })
    
    # Get latest snapshot
    if snapshots:
        latest = snapshots[-1]['url']
        resp = requests.get(latest)
        soup2 = BeautifulSoup(resp.text, 'html.parser')
        
        title = soup2.find('meta', property='og:title')
        desc = soup2.find('meta', property='og:description')
        
        return {
            'snapshots': snapshots[:10],
            'latest': {
                'name': title['content'] if title else None,
                'bio': desc['content'] if desc else None,
                'date': snapshots[-1]['date']
            }
        }
    return None
    
    
    
    
                  
                      METHOD 2:---     Google Cache
                      URL Pattern:---   https://webcache.googleusercontent.com/search?q=cache:t.me/{username}
                      Data Available:---
                                        - Last cached version of profile 
                                        - Recent bio/name
                                        - Profile photo (cached) 
                      Limitation:---   Unpredictable caching, may not be available

    Implementation: Web scraping

import requests
from bs4 import BeautifulSoup

def google_cache(username):
    url = f"https://webcache.googleusercontent.com/search?q=cache:t.me/{username}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('meta', property='og:title')
            desc = soup.find('meta', property='og:description')
            
            return {
                'name': title['content'] if title else None,
                'bio': desc['content'] if desc else None,
                'cached_date': response.headers.get('Date')
            }
    except:
        pass
    return None
    
    
    
    
    
                       METHOD 3:---      Telegram Search Engines
                       URL Pattern:---   Various search engines
                       Data Available:---
                                         - Public mentions across platforms 
                                         - Group/channel references 
                                         - Cross-platform links
                                         
    Implementation:---   Web Scarping
    
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

def telegram_search_engines(username):
    searches = [
        f'"{username}" "telegram"',
        f'"t.me/{username}"',
        f'"@{username}" "telegram"'
    ]
    
    results = {}
    for query in searches:
        # Using DuckDuckGo API
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json"
        response = requests.get(url)
        data = response.json()
        results[query] = data.get('RelatedTopics', [])
    
    return results
    
    
    
    

                           METHOD 4:---  Cryptocurrency Wallet Tracking
                           URL Pattern:---
                                         - Ethereum: https://etherscan.io/search?q={username}
                                         - Bitcoin: https://blockchair.com/search?q={username}
                                         - Solana: https://solscan.io/search?q={username}
                            Data Available:---
                                              - Wallet addresses  
                                              - Transaction history
                                              - Token holdings
                                              - Exchange links

                             Limitation:---   Only if username is associated with crypto
                             
    Implementation:---    Web Scarping
    
import requests

def crypto_wallet_search(username):
    platforms = {
        'etherscan': f'https://etherscan.io/search?q={username}',
        'blockchair': f'https://blockchair.com/search?q={username}',
        'solscan': f'https://solscan.io/search?q={username}'
    }
    
    results = {}
    for platform, url in platforms.items():
        try:
            response = requests.get(url)
            results[platform] = {
                'exists': response.status_code == 200,
                'url': url
            }
        except:
            results[platform] = {'exists': False}
    
    return results
    
    
    
    
                             METHOD 5:----    Domain WHOIS Lookup
                             URL Pattern:---   https://who.is/whois/{username}.com
                             Data Available:---
                                               - Registered domains with username
                                               - Contact information
                                               - Registration/Expiry dates
                                               - Nameservers
                                               
     Implementation:---   Web Scarping
     
import requests
from bs4 import BeautifulSoup

def whois_lookup(username):
    tlds = ['.com', '.org', '.net', '.io', '.tech']
    results = []
    
    for tld in tlds:
        domain = f"{username}{tld}"
        url = f"https://who.is/whois/{domain}"
        
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if 'No match for' not in response.text:
                registrar = soup.find('td', string='Registrar')
                creation = soup.find('td', string='Creation Date')
                expiry = soup.find('td', string='Expiration Date')
                
                results.append({
                    'domain': domain,
                    'registered': True,
                    'registrar': registrar.find_next('td').text if registrar else None,
                    'creation_date': creation.find_next('td').text if creation else None,
                    'expiry_date': expiry.find_next('td').text if expiry else None
                })
            else:
                results.append({
                    'domain': domain,
                    'registered': False
                })
        except:
            pass
    
    return results
    
    
    
    
    
                            METHOD 6:---    Social Media Username Search
                            URL Pattern:---   Various platforms
                            Data Available:--- 
                                             - Same username across platforms
                                             - Cross-platform activity
                                             - Profile correlation
                                             
    Implementation:---  HTTP requests (check if profile exists)
    
import requests
import time

def social_media_search(username):
    platforms = {
        'twitter': f'https://twitter.com/{username}',
        'instagram': f'https://www.instagram.com/{username}/',
        'github': f'https://github.com/{username}',
        'reddit': f'https://www.reddit.com/user/{username}',
        'youtube': f'https://www.youtube.com/@{username}',
        'linkedin': f'https://www.linkedin.com/in/{username}',
        'facebook': f'https://www.facebook.com/{username}',
        'tiktok': f'https://www.tiktok.com/@{username}',
        'pinterest': f'https://www.pinterest.com/{username}/',
        'medium': f'https://medium.com/@{username}'
    }
    
    results = {}
    for platform, url in platforms.items():
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                # Check if it's an actual profile (not error page)
                if 'not found' not in response.text.lower():
                    results[platform] = {'exists': True, 'url': url}
                else:
                    results[platform] = {'exists': False}
            else:
                results[platform] = {'exists': False}
        except:
            results[platform] = {'exists': False}
        time.sleep(0.5)
    
    return results
    
    
    
    
    
                                 METHOD 6:---    Username Search on Code Repositories
                                 URL Pattern:--- GitHub, GitLab, Bitbucket, etc.
                                 Data Available:--- 
                                                  - Code repositories
                                                  - Commits with username
                                                  - README mentions
                                                  - Config files
                                                  
    Implementation:---     Api / Web Scarping
    
import requests

def code_repo_search(username):
    # GitHub search
    github_url = f"https://api.github.com/search/code?q=t.me/{username}"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    
    try:
        response = requests.get(github_url, headers=headers)
        github_data = response.json() if response.status_code == 200 else {}
        
        # GitLab search (alternative)
        gitlab_url = f"https://gitlab.com/api/v4/projects?search={username}"
        gitlab_response = requests.get(gitlab_url)
        gitlab_data = gitlab_response.json() if gitlab_response.status_code == 200 else []
        
        return {
            'github': {
                'total_count': github_data.get('total_count', 0),
                'items': [{'path': item['path'], 'url': item['html_url']} 
                         for item in github_data.get('items', [])[:5]]
            },
            'gitlab': {
                'projects': [{'name': p['name'], 'url': p['web_url']} 
                            for p in gitlab_data[:5]]
            }
        }
    except:
        return {'error': 'Search failed'}
        
        
        
        
        
                                     METHOD 7:---      Pastebin and Snippet Sites
                                     URL Pattern:---   https://pastebin.com/search?q={username}
                                     Data Available:---
                                                       - Pastes mentioning username
                                                       - Source code snippets 
                                                       - Configuration files
                                                       - Leaked credentials
    Implementation: Web scraping

import requests
from bs4 import BeautifulSoup

def pastebin_search(username):
    queries = [
        f"{username} telegram",
        f"t.me/{username}",
        f"@{username}"
    ]
    
    results = []
    for query in queries:
        url = f"https://pastebin.com/search?q={query}"
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for paste in soup.find_all('div', class_='paste'):
                title = paste.find('a')
                description = paste.find('div', class_='paste_description')
                
                if title:
                    results.append({
                        'title': title.text,
                        'url': f"https://pastebin.com{title.get('href')}",
                        'description': description.text if description else None
                    })
        except:
            pass
    
    return results




    
                                  METHOD 8:---   Telegram Channel Directory Sites
                                  URL Pattern:---
                                               - https://t.me/s/{keyword}
                                               - https://telegramchannels.me/search?q={username} 
                                               - https://tlgrm.eu/search?q={username}
                                  Data Available:---
                                                   - Public channel list
                                                   - Channel descriptions
                                                   - Category/niche
                                                   - Subscriber count

    Implementation: Web scraping
                           
import requests
from bs4 import BeautifulSoup

def channel_directory_search(username):
    directories = [
        f"https://t.me/s/{username}",
        f"https://telegramchannels.me/search?q={username}",
        f"https://tlgrm.eu/search?q={username}"
    ]
    
    results = []
    for url in directories:
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract channel info
            channels = soup.find_all('div', class_='channel-item')
            for channel in channels:
                name = channel.find('div', class_='channel-name')
                desc = channel.find('div', class_='channel-description')
                
                results.append({
                    'name': name.text if name else None,
                    'description': desc.text if desc else None,
                    'source': url
                })
        except:
            pass
    
    return results
    
    
    
    
    
                                    METHOD 9:---    File Type Search for Username
                                    URL Pattern:---   Search engine queries
                                    Data Available:---
                                                     - Documents containing username
                                                     - PDF, DOC, TXT, JSON files with references
    
    Implementation: DuckDuckGo API/Google
                                                     
import requests
from urllib.parse import quote

def file_search(username):
    file_types = ['pdf', 'doc', 'docx', 'txt', 'json', 'xml', 'csv']
    results = {}
    
    for ext in file_types:
        query = f'"{username}" filetype:{ext}'
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json"
        
        try:
            response = requests.get(url)
            data = response.json()
            results[ext] = {
                'count': len(data.get('RelatedTopics', [])),
                'topics': data.get('RelatedTopics', [])[:3]
            }
        except:
            results[ext] = {'count': 0, 'topics': []}
    
    return results
    
    
    
    
    
                                      METHOD 10:---     Whois Domain History
                                      URL Pattern:---   https://whois.domainhistory.com/domain/{username}.com
                                      Data Available:---
                                                        - Historical domain ownership
                                                        - Previous owners
                                                        - Domain changes

    Implementation:---   Web Scarping
    
import requests
from bs4 import BeautifulSoup

def domain_history(username):
    domains = [f"{username}.com", f"{username}.org"]
    results = []
    
    for domain in domains:
        url = f"https://whois.domainhistory.com/domain/{domain}"
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract history entries
            history_entries = soup.find_all('div', class_='history-entry')
            for entry in history_entries:
                date = entry.find('span', class_='date')
                change = entry.find('span', class_='change')
                
                results.append({
                    'domain': domain,
                    'date': date.text if date else None,
                    'change': change.text if change else None
                })
        except:
            pass
    
    return results
    
    
    
    
    
                                    METHOD 11:---     Academic/Scientific Search
                                    URL Pattern:---   https://scholar.google.com/scholar?q={username}+telegram
                                    Data Available:---
                                                      - Research papers
                                                      - Academic mentions
                                                      - Publications

    Implementation: Web scraping
    
import requests
from bs4 import BeautifulSoup

def academic_search(username):
    url = f"https://scholar.google.com/scholar?q={username}+telegram"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for paper in soup.find_all('div', class_='gs_or')[:10]:
            title = paper.find('h3')
            authors = paper.find('div', class_='gs_a')
            
            results.append({
                'title': title.text if title else None,
                'authors': authors.text if authors else None
            })
        
        return results
    except:
        return []
        
        
        
        
        
                                        METHOD 12:---     News/Mentions Search
                                        URL Pattern:---   https://news.google.com/search?q={username}+telegram
                                        Data Available:---
                                                         - News articles mentioning username 
                                                         - Press releases
                                                         - Media coverage

    Implementation: Web scraping
    
import requests
from bs4 import BeautifulSoup

def news_search(username):
    url = f"https://news.google.com/search?q={username}+telegram"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for article in soup.find_all('article')[:10]:
            title = article.find('h3')
            source = article.find('div', class_='source')
            time = article.find('time')
            
            results.append({
                'title': title.text if title else None,
                'source': source.text if source else None,
                'date': time.get('datetime') if time else None
            })
        
        return results
    except:
        return []
        
        
        
        
        
                                        METHOD 13:---       Dark Web Search (Special Cases)
                                         Note:---            For legal investigations only with proper authorization
                                         Data Available:---
                                                          - Telegram mentions on dark web
                                                          - Leaked databases
                                                          - Underground forum references

    Implementation:---   Tor + Scraping (requires specialized setup)
    
# Only for legal authorized investigations
import requests
from stem import Signal
from stem.control import Controller

def dark_web_search(username):
    # Setup Tor proxy
    session = requests.Session()
    session.proxies = {
        'http': 'socks5h://127.0.0.1:9050',
        'https': 'socks5h://127.0.0.1:9050'
    }
    
    # Search on dark web search engines
    searches = [
        f"http://ahmia.fi/search/?q={username}+telegram",
        f"http://onion.city/search?q={username}"
    ]
    
    results = []
    for url in searches:
        try:
            response = session.get(url, timeout=30)
            # Parse results
            results.append({
                'source': url,
                'status': 'checked'
            })
        except:
            pass
    
    return results
    
    
    
    
    
                                        METHOD 14:---     Email Breach Check
                                        URL Pattern:---   https://haveibeenpwned.com/api/v3/breachedaccount/{email}
                                        Data Available:---
                                                         - Breached accounts
                                                         - Data leaks
                                                         - Compromised credentials
                                                         
    Implementation: API (free, rate limited) 
    
import requests

def breach_check(username):
    # Create possible email addresses
    emails = [
        f"{username}@gmail.com",
        f"{username}@yahoo.com",
        f"{username}@outlook.com"
    ]
    
    results = {}
    for email in emails:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
        headers = {'hibp-api-key': 'YOUR_API_KEY'}  # Optional for higher rate limits
        
        try:
            response = requests.get(url)
            if response.status_code == 200:
                results[email] = response.json()
            else:
                results[email] = []
        except:
            results[email] = {'error': 'API request failed'}
    
    return results
    
    
        
        
    
SECTION 5 :----       INTELLIGENCE GATHERING PRIORITY    -------------------------------------------------------------



                    Phase 1:---   Basic Intel (P0 - P1)

                              Always Available - No Special Access Required

                                       Priority	             Data Point	                  Method	                              Section	          Implementation
                                          P0	                 Username Exists	             t.me scraping	                       2.1	              requests.get(url).status_code
                                          P0                 Display Name	             t.me scraping	                       2.1	              og:title meta tag
                                          P0                 Bio/Description	             t.me scraping	                       2.1	              og:description meta tag
                                          P0                 Profile Photo	             t.me scraping	                       2.1	              og:image meta tag
                                          P0	                 User                        ID	@userinfobot	                       1.1	              Send username to bot
                                          P1                 Account Creation Date	     @userinfobot	                       1.1	              First seen date
                                          P1                 Online Status	             t.me scraping	                       2.1	              Last seen (if public)
                                          P1                 Public Channel Messages	     t.me/s/ scraping	                   2.2	              Channel message extraction
                                          
                                          
    Implementation Example:

import requests
from bs4 import BeautifulSoup

class BasicIntel:
    """Phase 1: Basic Intelligence Gathering"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def check_username_exists(self, username):
        """P0: Check if username exists"""
        url = f"https://t.me/{username}"
        try:
            response = self.session.get(url)
            return {
                'exists': response.status_code == 200,
                'username': username
            }
        except:
            return {'exists': False, 'error': 'Request failed'}
    
    def get_basic_profile(self, username):
        """P0: Get basic profile data"""
        url = f"https://t.me/{username}"
        try:
            response = self.session.get(url)
            if response.status_code != 200:
                return {'error': 'Profile not found'}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            title = soup.find('meta', property='og:title')
            description = soup.find('meta', property='og:description')
            image = soup.find('meta', property='og:image')
            
            return {
                'username': username,
                'name': title['content'] if title else None,
                'bio': description['content'] if description else None,
                'photo': image['content'] if image else None,
                'exists': True
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_channel_messages(self, channel_name, limit=20):
        """P1: Get public channel messages"""
        url = f"https://t.me/s/{channel_name}"
        try:
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            messages = []
            for msg in soup.find_all('div', class_='tgme_widget_message')[:limit]:
                text = msg.find('div', class_='tgme_widget_message_text')
                date = msg.find('time')
                views = msg.find('span', class_='tgme_widget_message_views')
                
                messages.append({
                    'text': text.text if text else None,
                    'date': date['datetime'] if date else None,
                    'views': views.text if views else '0'
                })
            
            return messages
        except:
            return []
            
            
            
            
                
                        Phase 2:---    Enhanced Intel (P1 - P2)
                        
                              Requires Research & Cross-Referencing

                                  Priority	                  Data Point	                  Method	                      Section	                        Implementation 
                                     P1	                      Previous Usernames          @SangMataInfo_bot	            1.2	                            Send username to bot
                                     P1	                      Previous Usernames          Wayback Machine	            4.A	                            Archive.org snapshots
                                     P1	                      Group Memberships	          @tgdb_bot	                    1.3	                            Send username to bot
                                     P1      	              Group Memberships	          TelegramDB.org	                2.12         	                Web scraping
                                     P1	                      Cross-Platform              Mentions	Google Dorking	    2.3	                            Search engine queries
                                     P1	                      Cross-Platform Mentions	  DuckDuckGo Search	            2.6	                            API queries
                                     P1	                      Email/Phone in Bio	Email     Harvesting	                    2.9	                            Regex extraction
                                     P1	                      Channel Statistics     	  TGStat.com	                    2.21       	                    Web scraping
                                     P1	                      Channel Analytics	          Telemetr.io	                2.22         	                Web scraping
                                     P2	                      Creation Date	              @userinfobot	                1.1	                            First seen date
                                     P2	                      Activity Patterns	          Message Analysis	            2.2	                            Message frequency
                                     P2              	      Social Media Profiles	      Cross-Platform Search	        2.10    	                        HTTP requests
                                     P2	                      Domain Registration	      WHOIS Lookup	                4.E  	                        Web scraping
                                     P2	                      Historical Profile	          Google Cache	                4.B	                            Cache checking 
                                     P2	                      Code References	          GitHub Search	                2.16           	                GitHub API
                                     
                                     
    Implementation Example:

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import quote

class EnhancedIntel:
    """Phase 2: Enhanced Intelligence Gathering"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_previous_usernames(self, username):
        """P1: Get previous usernames via Wayback Machine"""
        url = f"https://web.archive.org/web/*/https://t.me/{username}"
        try:
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            previous = []
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and 'web/' in href:
                    snapshot_url = f"https://web.archive.org{href}"
                    # Check snapshot for previous username
                    snap_resp = self.session.get(snapshot_url)
                    snap_soup = BeautifulSoup(snap_resp.text, 'html.parser')
                    
                    title = snap_soup.find('meta', property='og:title')
                    if title:
                        # Extract username from title if different
                        previous.append({
                            'date': link.text.strip(),
                            'name': title.get('content') if title else None
                        })
            
            return previous[:10]
        except:
            return {'error': 'Wayback check failed'}
    
    def get_group_memberships(self, username):
        """P1: Find groups where username appears"""
        # Method 1: TelegramDB
        db_url = f"https://telegramdb.org/search?q={username}"
        groups = []
        
        try:
            response = self.session.get(db_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for item in soup.find_all('div', class_='result-item')[:10]:
                title = item.find('h3')
                desc = item.find('p')
                link = item.find('a')
                
                groups.append({
                    'name': title.text if title else None,
                    'description': desc.text if desc else None,
                    'url': link.get('href') if link else None,
                    'source': 'TelegramDB'
                })
        except:
            pass
        
        # Method 2: Google Dorking
        dorks = [
            f'"{username}" "t.me" group',
            f'"{username}" "joinchat"'
        ]
        
        for dork in dorks:
            try:
                query = quote(dork)
                url = f"https://api.duckduckgo.com/?q={query}&format=json"
                response = self.session.get(url)
                data = response.json()
                
                for topic in data.get('RelatedTopics', []):
                    if 't.me' in str(topic):
                        groups.append({
                            'mention': topic,
                            'source': 'DuckDuckGo'
                        })
            except:
                pass
        
        return groups
    
    def cross_platform_mentions(self, username):
        """P1: Find username on other platforms"""
        platforms = {
            'twitter': f'https://twitter.com/search?q=@{username}%20telegram',
            'reddit': f'https://www.reddit.com/search/?q=telegram%20@{username}',
            'github': f'https://github.com/search?q=t.me%2F{username}'
        }
        
        results = {}
        for platform, url in platforms.items():
            try:
                response = self.session.get(url, timeout=5)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # Count mentions (simplified)
                    mention_count = len(re.findall(username, response.text.lower()))
                    results[platform] = {
                        'found': True,
                        'mention_count': mention_count
                    }
                else:
                    results[platform] = {'found': False}
            except:
                results[platform] = {'found': False}
            time.sleep(0.5)
        
        return results
    
    def extract_contact_info(self, username):
        """P1: Extract emails/phones from profile"""
        url = f"https://t.me/{username}"
        try:
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            desc = soup.find('meta', property='og:description')
            bio = desc['content'] if desc else ''
            
            # Extract emails
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, bio)
            
            # Extract phones
            phone_pattern = r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
            phones = re.findall(phone_pattern, bio)
            
            return {
                'emails': list(set(emails)),
                'phones': list(set(phones))
            }
        except:
            return {'emails': [], 'phones': []}
    
    def get_channel_stats(self, channel_name):
        """P1: Get channel statistics from TGStat"""
        url = f"https://tgstat.com/search?q={channel_name}"
        try:
            response = self.session.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            stats = []
            for item in soup.find_all('div', class_='search-item')[:5]:
                name = item.find('div', class_='search-item-title')
                subscribers = item.find('div', class_='search-item-stats')
                
                if name:
                    link = name.find('a')
                    stats.append({
                        'channel': link.text if link else None,
                        'subscribers': re.findall(r'[\d,]+', subscribers.text)[0] if subscribers else '0'
                    })
            
            return stats
        except:
            return {'error': 'TGStat search failed'}
    
    def get_social_profiles(self, username):
        """P2: Find social media profiles with same username"""
        platforms = {
            'instagram': f'https://www.instagram.com/{username}/',
            'twitter': f'https://twitter.com/{username}',
            'github': f'https://github.com/{username}',
            'reddit': f'https://www.reddit.com/user/{username}',
            'youtube': f'https://www.youtube.com/@{username}'
        }
        
        results = {}
        for platform, url in platforms.items():
            try:
                response = self.session.get(url, timeout=5)
                if response.status_code == 200:
                    # Check if it's an actual profile page
                    soup = BeautifulSoup(response.text, 'html.parser')
                    if 'not found' not in response.text.lower():
                        results[platform] = {'exists': True, 'url': url}
                    else:
                        results[platform] = {'exists': False}
                else:
                    results[platform] = {'exists': False}
            except:
                results[platform] = {'exists': False}
            time.sleep(0.3)
        
        return results
        
        
        
        
        
                     Phase 3: Deep Intel (P2 - P3)
                       
                       Requires API Access or Special Authorization

                                 Priority	           Data Point	        Method	            Section	                  Implementation
                                   P2	               Phone Number	       MTProto API	         3.1         	          Telethon get_entity() 
                                   P2	               Online Patterns	   MTProto API	         3.6      	              Status tracking
                                   P2	               Message History	   MTProto API	         3.2	                      get_messages()
                                   P2	               Full Profile	       MTProto API	         3.10	                  get_user()
                                   P2	               Media Files	       MTProto API	         3.7       	              download_media()
                                   P2	               Forward Tracking	   MTProto API	         3.15	                  message.forward
                                   P3	               Common Contacts	   MTProto API	         3.3   	                  get_common_chats()
                                   P3	               Group Members 	   MTProto API	         3.4  	                  get_participants()
                                   P3	               All Dialogs	       MTProto API	         3.8 	                  get_dialogs()
                                   P3	               Channel Admin List  MTProto API	         3.14	                  get_participants()
                                   P3	               Search Messages	   MTProto API	         3.11	                  get_messages(search=)
                                   P3	               Contact List	       MTProto API	         3.12	                  get_contacts()

    Implementation Example:
    
from telethon import TelegramClient
from telethon.errors import FloodWaitError
import asyncio
import json

class DeepIntel:
    """Phase 3: Deep Intelligence (Requires API)"""
    
    def __init__(self, api_id, api_hash):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = TelegramClient('session', api_id, api_hash)
    
    async def start(self):
        """Initialize API connection"""
        await self.client.start()
    
    async def get_full_profile(self, username):
        """P2: Get complete user profile"""
        try:
            user = await self.client.get_entity(username)
            return {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone': user.phone if hasattr(user, 'phone') else None,
                'premium': user.premium if hasattr(user, 'premium') else False,
                'verified': user.verified if hasattr(user, 'verified') else False,
                'bot': user.bot,
                'status': str(user.status) if hasattr(user, 'status') else None
            }
        except Exception as e:
            return {'error': str(e)}
    
    async def get_message_history(self, username, limit=100):
        """P2: Get message history"""
        try:
            user = await self.client.get_entity(username)
            messages = await self.client.get_messages(user, limit=limit)
            
            return [{
                'text': msg.text,
                'date': str(msg.date),
                'has_media': bool(msg.media),
                'forwarded': bool(msg.forward),
                'id': msg.id
            } for msg in messages]
        except Exception as e:
            return {'error': str(e)}
    
    async def get_media_files(self, username, limit=10):
        """P2: Download media files"""
        try:
            user = await self.client.get_entity(username)
            messages = await self.client.get_messages(user, limit=limit)
            
            media_files = []
            for msg in messages:
                if msg.media:
                    path = await self.client.download_media(msg)
                    media_files.append({
                        'path': path,
                        'date': str(msg.date),
                        'type': str(type(msg.media).__name__)
                    })
            
            return media_files
        except Exception as e:
            return {'error': str(e)}
    
    async def get_common_groups(self, username):
        """P3: Get common groups with user"""
        try:
            target = await self.client.get_entity(username)
            common = await self.client.get_common_chats(target)
            
            return [{
                'id': chat.id,
                'title': chat.title,
                'type': 'group' if chat.is_group else 'channel'
            } for chat in common]
        except Exception as e:
            return {'error': str(e)}
    
    async def get_group_participants(self, group_username, limit=50):
        """P3: Get group participants"""
        try:
            group = await self.client.get_entity(group_username)
            participants = await self.client.get_participants(group, limit=limit)
            
            return [{
                'id': p.id,
                'username': p.username,
                'first_name': p.first_name,
                'last_name': p.last_name,
                'online': p.status is not None
            } for p in participants]
        except Exception as e:
            return {'error': str(e)}
    
    async def get_contacts(self):
        """P3: Get user's contact list"""
        try:
            contacts = await self.client.get_contacts()
            
            return [{
                'id': c.id,
                'username': c.username,
                'first_name': c.first_name,
                'last_name': c.last_name,
                'phone': c.phone
            } for c in contacts]
        except Exception as e:
            return {'error': str(e)}
    
    async def search_messages(self, username, keyword, limit=50):
        """P3: Search messages by keyword"""
        try:
            user = await self.client.get_entity(username)
            messages = await self.client.get_messages(user, search=keyword, limit=limit)
            
            return [{
                'text': msg.text,
                'date': str(msg.date),
                'matches': keyword in msg.text if msg.text else False
            } for msg in messages]
        except Exception as e:
            return {'error': str(e)}
    
    async def get_user_status(self, username):
        """P2: Get detailed user status"""
        try:
            user = await self.client.get_entity(username)
            
            status_info = {
                'username': username,
                'status_type': str(type(user.status).__name__)
            }
            
            if hasattr(user.status, 'was_online'):
                status_info['last_seen'] = str(user.status.was_online)
            
            if hasattr(user.status, 'is_online'):
                status_info['online'] = user.status.is_online
            
            return status_info
        except Exception as e:
            return {'error': str(e)}
    
    async def close(self):
        """Close API connection"""
        await self.client.disconnect()

# Usage
async def main():
    intel = DeepIntel(api_id=123456, api_hash='your_hash')
    await intel.start()
    
    # Get full profile
    profile = await intel.get_full_profile('username')
    print(json.dumps(profile, indent=2))
    
    # Get messages
    messages = await intel.get_message_history('username', limit=20)
    print(f"Found {len(messages)} messages")
    
    await intel.close()

asyncio.run(main())





SECTION 6:----        IMPLEMENTATION FOR OUR TOOL   --------------------------------------------------------------------------------------------------------------

                  What We Can Implement WITHOUT Telegram API:--------
                  
1.  t.me Profile Scraping → Name, Bio, Photo

import requests
from bs4 import BeautifulSoup

def scrape_profile(username):
    url = f"https://t.me/{username}"
    response = requests.get(url)
    
    if response.status_code != 200:
        return {'exists': False}
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    title = soup.find('meta', property='og:title')
    desc = soup.find('meta', property='og:description')
    img = soup.find('meta', property='og:image')
    
    return {
        'exists': True,
        'name': title['content'] if title else None,
        'bio': desc['content'] if desc else None,
        'photo': img['content'] if img else None
    }
    
    
    
    
2.  t.me/s/ Channel Messages → Content Analysis

def scrape_channel_messages(channel_name, limit=50):
    url = f"https://t.me/s/{channel_name}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    messages = []
    for msg in soup.find_all('div', class_='tgme_widget_message')[:limit]:
        text = msg.find('div', class_='tgme_widget_message_text')
        date = msg.find('time')
        views = msg.find('span', class_='tgme_widget_message_views')
        
        messages.append({
            'text': text.text if text else None,
            'date': date['datetime'] if date else None,
            'views': views.text if views else '0'
        })
    
    return messages
    
    
    
    
    
3.   Google Dorking → Cross-References

from urllib.parse import quote

def google_dork(username):
    dorks = [
        f'"{username}" site:t.me',
        f'"@{username}" site:t.me',
        f'"{username}" "telegram" group'
    ]
    
    results = []
    for dork in dorks:
        query = quote(dork)
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        response = requests.get(url)
        data = response.json()
        results.extend(data.get('RelatedTopics', []))
    
    return results
    
    
    
    
    
4.   Wayback Machine → Historical Data

def wayback_check(username):
    url = f"https://web.archive.org/web/*/https://t.me/{username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    snapshots = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and 'web/' in href:
            snapshots.append({
                'url': f"https://web.archive.org{href}",
                'date': link.text.strip()
            })
    
    return snapshots[:10]
    
    
    
    
    
5.  TelegramDB → Search Results

def search_telegramdb(username):
    url = f"https://telegramdb.org/search?q={username}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    for item in soup.find_all('div', class_='result-item')[:20]:
        title = item.find('h3')
        desc = item.find('p')
        link = item.find('a')
        
        results.append({
            'title': title.text if title else None,
            'description': desc.text if desc else None,
            'url': link.get('href') if link else None
        })
    
    return results
    
    
    
    
    
6. DuckDuckGo Search → Public Mentions

def duckduckgo_search(username):
    url = f"https://api.duckduckgo.com/?q={username}+telegram&format=json"
    response = requests.get(url)
    data = response.json()
    
    return {
        'abstract': data.get('Abstract', ''),
        'related_topics': data.get('RelatedTopics', [])
    }
    
    
    
    
    


     



    
    
    
    
    
                

