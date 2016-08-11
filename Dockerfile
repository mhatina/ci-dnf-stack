FROM fedora:24
ENV LANG C

RUN echo "deltarpm=0" >> /etc/dnf/dnf.conf
# TODO: https://bugzilla.redhat.com/show_bug.cgi?id=1366287
RUN dnf -y update -x nss\*
RUN dnf -y install httpd /usr/bin/behave-2 python2-rpmfluff
COPY dnf-docker-test/repo /var/www/html/repo/
COPY dnf-docker-test/features /behave/

COPY rpms /rpms/
# TODO: COPR broken, drop --allowerasing
RUN dnf -y install /rpms/*.rpm --allowerasing
RUN dnf -y autoremove
RUN dnf -y clean all
RUN mkdir /tmp/repos.d && mv /etc/yum.repos.d/* /tmp/repos.d/

ADD dnf-docker-test/launch-test /usr/bin/
RUN mkdir /repo

VOLUME ["/junit"]
