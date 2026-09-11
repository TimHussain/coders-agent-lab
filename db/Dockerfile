FROM postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685
# The seeder uses Python's standard library and the image's psql: no second service.
RUN apk add --no-cache python3
COPY db/schema.sql /docker-entrypoint-initdb.d/01-schema.sql
COPY db/seed.py /opt/agentlab/seed.py
COPY db/02-seed.sh /docker-entrypoint-initdb.d/02-seed.sh
RUN chmod 755 /docker-entrypoint-initdb.d/02-seed.sh
