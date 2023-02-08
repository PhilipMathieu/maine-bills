import os
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

def pdf_to_txt(ld):
    reader = PdfReader("./pdf/"+ld+".pdf")

    lines = []
    for page in reader.pages[1:]:
        # Extract text from the whole page
        text_all = page.extract_text()
        # Split text at line breaks
        lines.extend(text_all.split('\n'))

    # Write all text to .txt
    with open("./txt/"+ld+".txt", 'w') as file:
        file.writelines([line + "\n" for line in lines])


directory = "http://lldc.mainelegislature.org/Open/LDs/131/"
res = requests.get(directory)
soup = BeautifulSoup(res.content)
hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]] # skip link to parent directory
lds = [href.split('/')[-1][:-4] for href in hrefs]

for ld in lds:
    if os.path.isfile("./txt/"+ld+".txt"):
        continue

    print("Processing {}".format(ld))

    # download the pdf
    res = requests.get(directory+ld+".pdf")
    with open('./pdf/'+ld+'.pdf', 'wb') as f:
        f.write(res.content)
    
    # perform the conversion
    pdf_to_txt(ld)

    # clean up
    os.remove('./pdf/'+ld+'.pdf')
