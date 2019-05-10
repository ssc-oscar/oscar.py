FROM ubuntu 

RUN apt update && apt -y install python-pip libtokyocabinet-dev

WORKDIR /home/python

COPY oscar.py requirements.txt setup.cfg setup.py test.py docs/ Makefile  ./

RUN pip install --no-cache-dir -r requirements.txt
