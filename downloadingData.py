
from selenium import webdriver

def newBrowser():
    return webdriver.Firefox()
         
browser=None


from lxml import html
from lxml.cssselect import CSSSelector
import time
import random

#Auxiliary functions to extract information from the browser

def loadPage(page,browser=browser):
    browser.get(page)
    return browser.page_source

def loadPageTree(page_source):
    tree = html.document_fromstring(page_source)
    return tree

def firstHouse(tree):
    element = tree.cssselect('.item-link')
    return element[0].get("href") if element else None

def getListOfHouses(tree):
    houses = [elem.get("href") for elem in tree.cssselect('.item-link')]
    return houses
    
def isLastPage(tree):
    return tree.cssselect(".icon-arrow-right-after") == []
    


# In[3]:


# Get the details of the house from the page

def getHouseData(tree):
    data = {}
    price = tree.cssselect(".info-data-price")
    data["price"] = price[0].text_content() if price else ""
    features = tree.cssselect(".info-features")
    data["features"] = [ it.text_content() for idx,it in enumerate(features[0].cssselect("span")) if idx%2==0]  if features else []
    descr = tree.cssselect(".adCommentsLanguage")
    data["description"] = descr[0].text_content() if descr else ""
    details = tree.cssselect(".details-property_features")
    if details:
        details_house = [ it.text_content() for it in details[0].cssselect("li")] 
        if len(details)>1:
            bdata = [d.cssselect("li") for d in details[1:]] 
            details_building = [ it.text_content() for d in bdata for it in d] 
        else:
            details_building = []
        energy = details[0].cssselect("span") 
        energy_class = energy[0].get("title") if energy else ""
    else:
        details_house = []
        details_building = []
        energy_class = ""
    data["details_house"] = details_house
    data["details_building"] = details_building
    data["energy_class"] = energy_class
    address = tree.cssselect("#headerMap")
    address_details = [it.text_content() for it in address[0].cssselect("li")][0:3] if address else []
    data["address"] = address_details
    
    return data


# In[4]:


import pymongo

# Connection to Mongo DB
try:
    conn=pymongo.MongoClient()
    print("connected")
except pymongo.errors.ConnectionFailure as e:
    print ("Could not connect to MongoDB: %s" % e )

db = conn["idealista"]
collection = db["house_data"]
urls = db["urls"]


# In[5]:


# In[6]:


def getHouseId(url): # /inmueble/id/ => id
    return url.split("/")[2]
    
def saveToMongo(houseUrl,data):
    house_id = getHouseId(houseUrl)
    data["id"] = house_id
    collection.replace_one( { "id" : house_id },   data, upsert = True )
    
def saveUrl(source,url):
    urls.insert_one( {"source":source , "url":url})
    


# In[7]:


# Method 1. Go to the first house page. From there go to the next indicated at "Siguiente"
#Not a good solution. Must keep browser open all the time.
#If browser closes you have to restart because you don't have a list of houses

def getNextHouseFromSource(page): #needed sometimes: for some reason getNextHouse fails
    text_next = 'class="btn nav next icon-arrow-right-after" href="'
    pstart = page.find(text_next)
    if pstart==-1:
        return None
    pstart += len(text_next)
    pend = page.find('"', pstart)+1
    return page[pstart:pend]

def getNextHouse(page,tree):
    next_link = tree.cssselect(".icon-arrow-right-after")
    next_house = next_link[0].get("href") if next_link else None
    if next_house is None: 
        next_house = getNextHouseFromSource(page)
    return next_house
    
def getHouses(from_start=True):   
    if from_start:
        p = loadPage("https://www.idealista.com/venta-viviendas/barcelona-barcelona/")
        t = loadPageTree(p)
        time.sleep(3)
        next_house = firstHouse(t)
    else:
        p = browser.page_source
        t = loadPageTree(p)
        next_house = getNextHouse(p,t)
        
    while next_house:
        print(next_house,end=" ")
        p = loadPage("https://www.idealista.com"+next_house)
        t = loadPageTree(p)
        data = getHouseData(t)
        saveToMongo(next_house,data)
        time.sleep(random.randint(43,59)+10*random.random())
        next_house = getNextHouse(p,t)
    print("done")
       


# In[22]:


#Method 2. First retrieve the list of all houses
#Then you can get houses' data one by one by number
#This way you can stop and restart the browser as needed

def pause():
    time.sleep(random.randint(30,59)+8*random.random())
    
def pageFormat(start,end,page):
    res = "https://www.idealista.com/venta-viviendas/barcelona-barcelona/"
    res += "con-precio-hasta_{},precio-desde_{}/{}".format(
        end,start, "pagina-{}.htm".format(page) if page>1 else "")
    return res

def saveUrls(tree):
    #global listHouses (not needed anymore, using mongo)
    l = getListOfHouses(tree)
    #listHouses.extend(l)
    for url in l: 
        saveUrl("idealista",url)
    return len(l)
        
def getAllHouseUrls(startPrice=50000,incPrice=30000,finalPrice=3000000,startPage=1,loopLimit=100):
    pageNumber = startPage
    price = startPrice
    incr = incPrice
    zeros = 0 # sanity check. If something goes wrong, there will be many 0 urls in sequence
    
    while (price<finalPrice) and (zeros<3) and (loopLimit>0):
        pageUrl = pageFormat(price,price+incr-1,pageNumber)
        print(pageUrl,end="")
        p = loadPage(pageUrl)
        t = loadPageTree(p)
        l = saveUrls(t)
        print(" (",l,")",loopLimit)
        zeros = 0 if l>0 else zeros+1
        pause()
        if isLastPage(t):
            price += incr
            pageNumber = 1
        else:
            pageNumber += 1
        loopLimit -= 1
    print("done")        
       


# In[9]:


def getHousesData(loopLimit=100,browser=browser):
    if browser is None:
        browser = newBrowser()
        time.sleep(5)
    # create a list of ursl, after a while the cursor is not available anymore
    l_urls = [url["url"] for url in urls.find() if "removed" not in url]
    random.shuffle(l_urls) # useful if threading
    #print(len(l_urls))
    if len(l_urls)<loopLimit: loopLimit = len(l_urls)
    for url in l_urls: 
        houseId = getHouseId(url)
        if collection.find({"id":houseId}).count()==0:
            print(".",end="")
            p = loadPage("https://www.idealista.com"+url,browser)
            remove_it = ("ya no está publicado en idealista" in p) or ("no hay ningún anuncio con ese código" in p)
            if remove_it:
                urls.update_one({"url":url},{"$set":{"removed":True}})
                #print("(removed)",end="")
                pause()
                continue
            t = loadPageTree(p)
            data = getHouseData(t)
            if data.get("price"):
                saveToMongo(url,data)
            else:
                print("error")
                
                return False
            pause()            
            loopLimit -= 1        
            if loopLimit<1: break
   
    print("done") 
    return True
        


# In[10]:


from threading import Thread,currentThread
t=[]


# In[23]:


def doIt():
    t = currentThread()
    browser = newBrowser()
    while getHousesData(25,browser) and not getattr(t,"kill",False):        
        time.sleep(300)
    browser.close()


# In[37]:

def main():
    for i in range(3):
        tr = Thread(target=doIt)
        t.append(tr)
        tr.start()
        time.sleep(1)

# In[38]:

def checkThreads():
    for i,tr in enumerate(t):
        if not tr.isAlive():
            del(t[i])
        else:
            print(tr)


def checkMongo():
    print(urls.find({"removed":True}).count())
    print(collection.count())




