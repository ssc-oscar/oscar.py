FROM gcc
FROM python:3 

#RUN apt update && apt -y install python-pip libtokyocabinet-dev
RUN apt update && apt install -y libtokyocabinet-dev

WORKDIR /home/python

COPY oscar.py requirements.txt setup.cfg setup.py test.py docs/ Makefile  ./

RUN python3 -m pip install --no-cache-dir -r requirements.txt
