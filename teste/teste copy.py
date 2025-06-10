import os
import unicodedata
import re
from pyzbar.pyzbar import decode
from pdf2image import convert_from_path, convert_from_bytes

def main():

    pdfs = [i for i in os.listdir() if '.pdf' in i]
    for pdf in pdfs:
        if 'DUA' in pdf:
            img = convert_from_path(pdf,500)[0]
            decoded = decode(img)
            if decoded:
                d = [d for d in decoded if d.type == 'I25']
                if d:
                    print(d[0].data.decode('utf-8'))
                    print(f'{d[0].data.decode('utf-8')} - {d[0].data.decode('utf-8')[27:37]}')


            #print(decoded)
            #print(decode(img))


main()
