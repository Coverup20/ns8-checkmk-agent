FROM rockylinux:9-minimal

# Installazione dipendenze base
RUN microdnf install -y \
    python3 \
    git \
    xinetd \
    && microdnf clean all

# Repository script CheckMK
RUN git clone https://github.com/nethesis/checkmk-tools.git /opt/checkmk-tools

# Porta agent CheckMK
EXPOSE 6556

# Entrypoint placeholder (da definire dopo feedback dev NS8)
CMD ["/bin/bash"]
