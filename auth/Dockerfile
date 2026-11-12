FROM quay.io/keycloak/keycloak:26.7.3 AS builder

ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_HTTP_RELATIVE_PATH=/auth

RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.7.3

COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY auth/realm.json /opt/keycloak/data/import/arga.json
COPY auth/client-scopes.ndjson /opt/arga/client-scopes.ndjson
COPY auth/client-arga-web.json /opt/arga/client-arga-web.json
COPY auth/client-claude-run.json /opt/arga/client-claude-run.json
COPY auth/sync.sh /opt/arga/sync.sh

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=10 \
  CMD bash -c 'exec 3<>/dev/tcp/127.0.0.1/9000 && printf "GET /auth/health/ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n" >&3 && grep -q "200 OK" <&3'

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
