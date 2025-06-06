import os
import unicodedata
import re
from pyzbar.pyzbar import decode
from pdf2image import convert_from_path, convert_from_bytes

def main():

    pdfs = [i for i in os.listdir() if '.pdf' in i]
    img = convert_from_path(pdfs[0],500)[0]
    print(decode(img)[0].data.decode('utf-8'))
main()
