FROM postgres:16-alpine

RUN apk add --no-cache bash curl restic

COPY backup/fingerprint.sql /usr/local/share/arga-backup/fingerprint.sql
COPY backup/arga-backup /usr/local/bin/arga-backup

ENTRYPOINT ["arga-backup"]
CMD ["serve"]
