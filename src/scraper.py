import os
import logging
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import argparse

# command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--session", default="131", type=str, help="number of the legislative session to run")
parser.add_argument("-o", "--output_dir", default="./131/", type=str, help="path to store working and output files in")
args = parser.parse_args()

def pdf_to_txt(ld):
    reader = PdfReader(args.output_dir+"pdf/"+ld+".pdf")

    lines = []
    for page in reader.pages:
        # Extract text from the whole page
        text_all = page.extract_text()
        # Split text at line breaks
        lines.extend(text_all.split('\n'))

    # Write all text to .txt
    with open(args.output_dir+"txt/"+ld+".txt", 'w') as file:
        file.writelines([line + "\n" for line in lines])

if __name__ == "__main__":
    
    LEG_SESSION = args.session
    DIRECTORY_URL = "http://lldc.mainelegislature.org/Open/LDs/"+LEG_SESSION+"/"

    # set up directories if necessary
    if not os.path.exists(os.path.join(args.output_dir, "pdf/")):
        os.makedirs(os.path.join(args.output_dir, "pdf/"))
    if not os.path.exists(os.path.join(args.output_dir, "txt/")):
        os.makedirs(os.path.join(args.output_dir, "txt/"))
    
    # start logging
    logging.basicConfig(handlers=[logging.FileHandler(args.output_dir+"scraper.log"),logging.StreamHandler()], level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    logging.info("######### NEW RUN #########")

    # download and parse list of PDF links from the URL
    res = requests.get(DIRECTORY_URL)
    soup = BeautifulSoup(res.content, features="html.parser")
    hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]] # skip link to parent directory
    lds = [href.split('/')[-1][:-4] for href in hrefs]

    # process the links
    new_count = 0
    for ld in lds:

        # skip anything that has already been added to the corpus
        if os.path.isfile(args.output_dir+"txt/"+ld+".txt"):
            logging.debug("{} already in corpus.".format(ld))
            continue

        # otherwise, start processing the bill    
        logging.info("Processing {}".format(ld))
        
        try:
            # try to download the pdf
            logging.debug("Downloading PDF for {}".format(ld))
            res = requests.get(DIRECTORY_URL+ld+".pdf", timeout=10)
            # try to write the content to a file
            with open(args.output_dir+'pdf/'+ld+'.pdf', 'wb') as f:
                f.write(res.content)
        except requests.exceptions.RequestException as e:
            # skip if fails. This happens somewhat frequently due to timeouts
            logging.warning("Download error for {}; will retry on next run".format(ld))
            print(e)
            continue
        except FileNotFoundError as e:
            logging.warning("Could not write pdf for {}; will retry on next run".format(ld))
            print(e)
            continue
        
        new_count += 1
        
        # perform the conversion
        logging.debug("Converting {}".format(ld))
        pdf_to_txt(ld)

        # clean up
        logging.debug("Removing PDF for {}".format(ld))
        os.remove(args.output_dir+'pdf/'+ld+'.pdf')
    
    os.rmdir(args.output_dir+'pdf/')
    
    logging.info("Added {} new bills to corpus.".format(new_count))
