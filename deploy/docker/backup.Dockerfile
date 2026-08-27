FROM ghcr.io/tensorchord/vchord-postgres:pg18-v1.1.1

COPY deploy/docker/database-backup.sh /usr/local/bin/cookfully-database-backup
COPY deploy/docker/backup-entrypoint.sh /usr/local/bin/cookfully-backup-entrypoint

RUN sed -i 's/\r$//' /usr/local/bin/cookfully-database-backup /usr/local/bin/cookfully-backup-entrypoint \
    && chmod +x /usr/local/bin/cookfully-database-backup /usr/local/bin/cookfully-backup-entrypoint

ENTRYPOINT ["cookfully-backup-entrypoint"]
CMD ["serve"]
