import os
import logging
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

logging.basicConfig(handlers=[logging.FileHandler("debug.log"),logging.StreamHandler()], level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")

def pdf_to_txt(ld):
    reader = PdfReader("./pdf/"+ld+".pdf")

    lines = []
    for page in reader.pages:
        # Extract text from the whole page
        text_all = page.extract_text()
        # Split text at line breaks
        lines.extend(text_all.split('\n'))

    # Write all text to .txt
    with open("./txt/"+ld+".txt", 'w') as file:
        file.writelines([line + "\n" for line in lines])

logging.info("######### NEW RUN #########")
directory = "http://lldc.mainelegislature.org/Open/LDs/131/"
res = requests.get(directory)
soup = BeautifulSoup(res.content, features="html.parser")
hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]] # skip link to parent directory
lds = [href.split('/')[-1][:-4] for href in hrefs]

new_count = 0
for ld in lds:
    if os.path.isfile("./txt/"+ld+".txt"):
        logging.debug("{} already in corpus.".format(ld))
        continue
        
    logging.info("Processing {}".format(ld))
    
    try:
        # download the pdf
        logging.debug("Downloading PDF for {}".format(ld))
        res = requests.get(directory+ld+".pdf", timeout=10)
    except requests.exceptions.RequestException as e:
        logging.warning("Download error for {}; will retry on next run".format(ld))
        continue
    
    new_count += 1
        
    with open('./pdf/'+ld+'.pdf', 'wb') as f:
        f.write(res.content)
    
    # perform the conversion
    logging.debug("Converting {}".format(ld))
    pdf_to_txt(ld)

    # clean up
    logging.debug("Removing PDF for {}".format(ld))
    os.remove('./pdf/'+ld+'.pdf')
   

logging.info("Added {} new bills to corpus.".format(new_count))
