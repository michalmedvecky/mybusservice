FROM ubuntu:16.04

RUN apt-get update && apt-get -y install python-dev python-pip git python-virtualenv
RUN mkdir /opt/mybusservice/
RUN cd /opt/mybusservice && git clone https://github.com/michalmedvecky/mybusservice.git 
RUN mv mybusservice/* && virtualenv app && rm -fr mybusservice
RUN . app/bin/activate
RUN pip install -r requirements.txt

CMD /opt/mybusservice/app.py

