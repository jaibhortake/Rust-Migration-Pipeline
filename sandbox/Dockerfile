# Sandbox image: every compile and every run of user code happens inside a container made from this.
# Containers get no network, memory/CPU/pids limits, no capabilities and a non-root user (see app/sandbox.py).
FROM rust:1-slim-bookworm

# Optional extra root CAs (*.crt) for networks that re-sign TLS, e.g. antivirus web shields.
# Only used while building the image; certs/*.crt is git-ignored.
COPY certs/ /usr/local/share/ca-certificates/extra/
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt RUSTUP_USE_CURL=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates g++ python3 python3-coverage coreutils \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && rustup component add clippy rustfmt

# Crates a migration may use (the mapping layer only suggests these). Fetched at image build time because
# jobs build with --offline: the sandbox has no network.
COPY prefetch /opt/prefetch
RUN cd /opt/prefetch && cargo fetch && cargo build --release --quiet && rm -rf target

RUN useradd -m -u 1000 runner && chown -R runner /usr/local/cargo
USER runner
WORKDIR /work
