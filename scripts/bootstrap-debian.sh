#!/bin/bash

# Bootstraps a fresh Debian 12 (Bookworm) VPS with everything this project
# needs on the host: git, Docker Engine + Compose plugin, a basic firewall,
# unattended security updates, and a swap file (small VPS boxes like Mikr.us
# tend to ship with little/no RAM headroom).
#
# Usage (on the target server):
#   chmod +x bootstrap-debian.sh   # needed once — scp/paste often drops the execute bit
#   sudo ./bootstrap-debian.sh
# Safe to re-run — every step checks whether it already applied.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Error: run as root (sudo ./scripts/bootstrap-debian.sh)" >&2
    exit 1
fi

if ! grep -q "^VERSION_CODENAME=bookworm" /etc/os-release 2>/dev/null; then
    echo "Warning: this script targets Debian 12 (bookworm)." >&2
    echo "Detected: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2-)" >&2
    read -r -p "Continue anyway? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || exit 1
fi

TARGET_USER="${SUDO_USER:-}"

echo "==> Updating apt and installing base packages"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    git \
    make \
    curl \
    wget \
    ca-certificates \
    gnupg \
    ufw \
    fail2ban \
    unattended-upgrades \
    htop \
    tmux \
    vim \
    rsync \
    zsh

echo "==> Installing Docker Engine + Compose plugin"
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        >/etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    echo "✅ Docker installed: $(docker --version)"
else
    echo "✅ Docker already installed: $(docker --version)"
fi

if [[ -n "$TARGET_USER" ]] && ! id -nG "$TARGET_USER" | grep -qw docker; then
    usermod -aG docker "$TARGET_USER"
    echo "✅ Added $TARGET_USER to the docker group (log out/in to take effect)"
fi

echo "==> Configuring firewall (ufw)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
echo "✅ ufw enabled: SSH, 80, 443 allowed"

echo "==> Enabling fail2ban"
systemctl enable --now fail2ban >/dev/null
echo "✅ fail2ban running"

echo "==> Enabling unattended security upgrades"
if [[ ! -f /etc/apt/apt.conf.d/20auto-upgrades ]]; then
    cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
fi
echo "✅ unattended-upgrades configured"

echo "==> Ensuring a swap file exists"
if [[ ! -f /swapfile ]] && ! swapon --show | grep -q .; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >>/etc/fstab
    echo "✅ 2G swap file created and enabled"
else
    echo "✅ swap already configured ($(swapon --show --noheadings | wc -l) device(s))"
fi

echo "==> Setting up a non-root sudo user"
read -r -p "Username for daily/admin login (leave empty to skip): " ADMIN_USER
if [[ -n "$ADMIN_USER" ]]; then
    if ! id "$ADMIN_USER" &>/dev/null; then
        adduser --disabled-password --gecos "" "$ADMIN_USER"
        echo "✅ user $ADMIN_USER created"
    else
        echo "✅ user $ADMIN_USER already exists"
    fi
    usermod -aG sudo,docker "$ADMIN_USER"
    echo "✅ $ADMIN_USER added to sudo and docker groups"

    ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"
    install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "$ADMIN_HOME/.ssh"
    touch "$ADMIN_HOME/.ssh/authorized_keys"

    echo "Paste a public SSH key for $ADMIN_USER (e.g. contents of your local ~/.ssh/id_ed25519.pub), or leave empty to skip:"
    read -r PUB_KEY
    if [[ -n "$PUB_KEY" ]] && ! grep -qF "$PUB_KEY" "$ADMIN_HOME/.ssh/authorized_keys"; then
        echo "$PUB_KEY" >>"$ADMIN_HOME/.ssh/authorized_keys"
        echo "✅ key added to $ADMIN_USER's authorized_keys"
    fi
    chmod 600 "$ADMIN_HOME/.ssh/authorized_keys"
    chown "$ADMIN_USER:$ADMIN_USER" "$ADMIN_HOME/.ssh/authorized_keys"

    if [[ -s "$ADMIN_HOME/.ssh/authorized_keys" ]]; then
        echo
        echo "⚠️  Before locking down root SSH login: open a NEW terminal (keep this one open)"
        echo "    and confirm you can log in and use sudo:"
        echo "      ssh $ADMIN_USER@<server-ip>"
        echo "      sudo -v"
        read -r -p "Confirmed that login works? Disable root SSH login + password auth now? [y/N] " harden
        if [[ "$harden" =~ ^[Yy]$ ]]; then
            sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
            sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
            systemctl reload sshd
            echo "✅ root SSH login and password auth disabled"
        else
            echo "⏭  skipped — root SSH login left as-is, re-run this script later once you've confirmed $ADMIN_USER works"
        fi
    else
        echo "⏭  no SSH key added for $ADMIN_USER — skipping root-login lockdown (would lock you out)"
    fi
else
    echo "⏭  skipped non-root user setup"
fi

echo "==> Installing oh-my-zsh"
OMZ_USER="${TARGET_USER:-root}"
OMZ_HOME="$(getent passwd "$OMZ_USER" | cut -d: -f6)"
if [[ ! -d "$OMZ_HOME/.oh-my-zsh" ]]; then
    su - "$OMZ_USER" -c \
        'sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended'
    chsh -s "$(command -v zsh)" "$OMZ_USER"
    echo "✅ oh-my-zsh installed for $OMZ_USER, default shell set to zsh"
else
    echo "✅ oh-my-zsh already installed for $OMZ_USER"
fi

echo
echo "Done. Next steps:"
echo "  1. Log out/in so docker group membership and the zsh shell change apply"
echo "  2. If you skipped the root-login lockdown, verify ${ADMIN_USER:-the admin user} + sudo work, then re-run this script"
echo "  3. git clone <this repo> and follow docs/docker.md 'First Setup'"
