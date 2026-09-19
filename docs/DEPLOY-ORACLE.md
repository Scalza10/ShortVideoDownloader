# Deploy to Oracle Cloud (Always Free)

About an hour, start to finish. You end with `https://<name>.duckdns.org/`
serving the board over HTTPS, on a machine that stays free indefinitely.

**What you create:** one **Arm compute instance** (VM.Standard.A1.Flex) running
Ubuntu, with Docker Compose for the app and Caddy for HTTPS. Oracle's Always
Free tier covers 4 OCPU and 24 GB of memory of Ampere Arm capacity, so this is
free for good, unlike Azure's 12 months.

**What you need on your PC:** PowerShell (it has `ssh` and `scp` built in) and
this repo.

**Two things about this guide.** The Oracle console's defaults are wrong for
this app in three places, each called out below with ⚠️. And Oracle gives no
hostname, so section 5 gets one from DuckDNS.

---

## 1. Account (10 min)

1. Sign up at <https://www.oracle.com/cloud/free/>. A card is needed to verify
   you, but Always Free resources are never charged for it.
2. **The home region you pick cannot be changed, and free Arm capacity only
   exists there.** Busy regions (US East, US West) run out of free Arm capacity
   more often than quieter ones.
3. Consider upgrading to **Pay As You Go** under *Billing & Cost Management →
   Upgrade and Manage Payment*. Always Free resources stay free, and it
   protects the instance from being reclaimed; see "Idle reclamation" below.

## 2. SSH key (2 min, on your PC)

```powershell
ssh-keygen -t rsa -b 4096 -f $HOME\.ssh\reels_oci
Get-Content $HOME\.ssh\reels_oci.pub     # copy this whole line for step 4
```

A passphrase is worth setting. You are then asked for it on every `ssh`, `scp`
and deploy, unless you load the key into `ssh-agent`; see "Typing the
passphrase once" below.

## 3. Network first (5 min)

⚠️ **Create the network before the instance.** The instance form can create a
VCN and subnet inline, but while it does, *Automatically assign public IPv4
address* stays greyed out with "You must select a public subnet".

1. Menu (☰) → *Networking → Virtual cloud networks*, compartment `<your
   tenancy> (root)`.
2. *Actions → Start VCN Wizard* → **Create VCN with Internet Connectivity**.
3. Name it `reels-vcn`, keep the defaults, *Next → Create*.
4. Open the VCN → *Security Lists* → **Default Security List** → *Add Ingress
   Rules*, and add these two. Getting them wrong is the single most common
   reason HTTPS fails later.

| Stateless | Source CIDR | Protocol | Source ports | **Destination ports** |
|-----------|-------------|----------|--------------|-----------------------|
| unticked | `0.0.0.0/0` | TCP | leave empty | `80` |
| unticked | `0.0.0.0/0` | TCP | leave empty | `443` |

Port 22 is already allowed by the wizard. Narrow its source to your own IP once
everything works.

## 4. Create the instance (10 min)

*Compute → Instances → Create instance*:

| Section | Setting | Value |
|---------|---------|-------|
| Image | Image | ⚠️ *Change image* → **Ubuntu** → **Canonical Ubuntu 24.04** |
| Shape | Shape | *Change shape* → **Ampere** → **VM.Standard.A1.Flex**, 2 OCPU / 12 GB |
| Networking | VCN | **Select existing**: `reels-vcn` and its **public** subnet |
| Networking | Public IPv4 | **Assign automatically: ON** |
| SSH keys | | **Paste public keys**, the line from step 2 |
| Boot volume | | defaults (up to 200 GB total is free) |

⚠️ **The image dropdown defaults to Oracle Linux, and its Ubuntu list still
offers 20.04.** Both bite later, so check the image twice:

- Oracle Linux logs in as `opc`, not `ubuntu`. Whatever key you paste, an
  `ubuntu@` login on it fails with `Permission denied (publickey, ...)`.
- On Ubuntu 20.04 (focal, end of life) the Docker install script aborts with
  `E: Unable to locate package docker-model-plugin`, and the OS gets no
  security updates.

The first command in section 6 verifies what you actually got.

**"Out of capacity"** for the Arm shape is normal. Try another Availability
Domain, drop to 1 OCPU / 6 GB, or retry later in the day.

When the instance is **Running**, copy its **Public IP address**.

**If you did create the instance without a public IP:** open the instance →
*Networking* (or *Attached VNICs* → the VNIC) → *IP administration* → ⋮ next to
the private IP → *Edit* → **Ephemeral public IP** → *Update*. An ephemeral
address belongs to the instance, survives stop and start, and is free; it is
released only if the instance is terminated.

## 5. Hostname with DuckDNS (3 min)

Oracle gives no DNS name, and Caddy needs one to get a certificate.

1. Sign in at <https://www.duckdns.org> and create a subdomain, for example
   `myreels`. Set its IP to the instance's public IP and *update ip*.
2. ⚠️ **Check it resolves before starting the app**, because Caddy asks Let's
   Encrypt for a certificate the moment it starts:

   ```powershell
   nslookup <name>.duckdns.org
   ```

   This is your `SITE_ADDRESS`. A no-signup alternative is `sslip.io`:
   `203-0-113-10.sslip.io` resolves to `203.0.113.10`.

## 6. Prepare the VM (10 min)

```powershell
ssh -i $HOME\.ssh\reels_oci ubuntu@<public-ip>
```

On the VM, confirm the image is what you wanted:

```bash
lsb_release -d      # expect: Ubuntu 24.04.x LTS
uname -m            # expect: aarch64
```

⚠️ **There are two firewalls, and both must allow 80 and 443.** Section 3
covered Oracle's; Ubuntu's own iptables rules on Oracle images reject
everything except SSH. Run these **before** installing Docker, so the saved
rules don't include Docker's:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
sudo iptables -L INPUT -n --line-numbers    # ACCEPT dpt:80 and dpt:443 above the REJECT line
```

Then install Docker:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

The `exit` matters: the Docker group only applies after you reconnect. No swap
is needed at 12 GB, and `WORKERS=2` is fine.

## 7. First deploy (10 min)

From the repo folder on your PC:

```powershell
git archive --format=tar.gz -o reels.tar.gz master
scp -i $HOME\.ssh\reels_oci reels.tar.gz ubuntu@<public-ip>:~
ssh -i $HOME\.ssh\reels_oci ubuntu@<public-ip>
```

On the VM:

```bash
mkdir -p ~/reels && tar -xzf ~/reels.tar.gz -C ~/reels && cd ~/reels
cp .env.example .env
openssl rand -hex 24          # API_KEY
openssl rand -hex 16          # INVITE_TOKEN
nano .env
```

Edit these lines in place (Ctrl+O, Enter, Ctrl+X to save):

```
API_KEY=<the first random value>
WEB_PASSCODE=<the passcode you give your friends>
INVITE_TOKEN=<the second random value>
SITE_ADDRESS=<name>.duckdns.org
```

Start it:

```bash
docker compose up -d --build          # first build takes 3-5 minutes
docker compose logs -f caddy          # wait for "certificate obtained successfully", then Ctrl+C
curl https://<name>.duckdns.org/health
```

`/health` should return `"status":"ok"` and `"ffmpeg":true`. Then open the site
on a phone, enter the passcode and paste a link. On Android, browser menu →
*Add to Home screen* puts the app in TikTok's share menu.

## Deploying later

From the repo folder on your PC, after committing:

```powershell
.\scripts\deploy.ps1
```

See **Deploy** in the README for what it does and its parameters.

## Changing a `.env` value

The app reads `.env` only at startup, and `docker compose restart` keeps the old
values. Use `up -d`, which recreates just the affected containers in a few
seconds without rebuilding:

```bash
cd ~/reels
nano .env
docker compose up -d
docker compose exec api printenv WEB_PASSCODE    # check a value took effect
```

Deploys never overwrite `.env`, so changes made here survive them. Like a
deploy, this restarts the app and empties the pile.

## Costs and limits

| Item | Always Free allowance | This setup uses |
|------|-----------------------|-----------------|
| Arm OCPU | 3,000 OCPU-hours/month | 2 OCPU ≈ 1,460 |
| Arm memory | 18,000 GB-hours/month | 12 GB ≈ 8,760 |
| Block storage | 200 GB | ~47 GB boot volume |
| Outbound data | 10 TB/month | far below it |
| Ephemeral public IP | free | 1 |

Running all month cannot exhaust the allowance at this size, and Always Free
does not expire after 12 months. Where to look:

- *Billing & Cost Management → Cost Analysis*: should stay at $0.00.
- *Billing & Cost Management → Budgets*: set a $1 budget with an email alert.
- *Billing & Cost Management → Subscriptions*: trial credit and days left.
- *Governance & Administration → Limits, Quotas and Usage*, service Compute:
  how much of the free Arm allowance is in use.

**Idle reclamation.** On accounts that never upgraded, Oracle may reclaim
Always Free compute instances that look idle over 7 days (low CPU, network and
memory). An app used by a handful of friends can look idle. Upgrading to Pay As
You Go exempts the instance and keeps Always Free resources free; pair it with
the $1 budget alert.

## When something goes wrong

| Symptom | Check |
|---------|-------|
| `Permission denied (publickey,gssapi-keyex,gssapi-with-mic)` | The `gssapi` methods mean Oracle Linux, so the image is wrong. `ssh -v` shows `OpenSSH_9.6p1 Ubuntu` on a correct one. Recreate with Ubuntu 24.04. |
| `Permission denied (publickey)` on a known-good key | The key has a passphrase and nothing supplied it, or a different key was pasted at creation. `ssh-keygen -lf ~/.ssh/authorized_keys` on the VM shows which key it accepts. |
| Docker install ends with `Unable to locate package docker-model-plugin` | The image is Ubuntu 20.04. Terminate and recreate with 24.04. |
| Caddy logs `Timeout during connect (likely firewall problem)` | Ports 80/443. Test from your PC: `Test-NetConnection <ip> -Port 443`. A timeout means the Security List (section 3); "refused" means iptables (section 6). Caddy retries every minute, so no restart is needed after fixing. |
| Caddy logs certificate errors naming the wrong address | `SITE_ADDRESS` must match the DuckDNS name exactly, and DuckDNS must point at this instance's current IP. |
| `/` returns 404 | `WEB_PASSCODE` is empty in `.env`; set it and run `docker compose up -d`. |
| Instagram fails with "requires a login" | Add a cookies file: see "Instagram cookies" in the README. |
| Downloads fail with "blocked" | The platform may be refusing Oracle's IP range, or `yt-dlp` is out of date; bump it in `requirements.txt` and deploy. |
| Instance disappeared | Idle reclamation on a free-only account; see above. |

App logs: `docker compose logs -f api`.

## Typing the passphrase once

Each deploy asks for the key passphrase twice (upload, then restart). To type it
once per Windows login, enable the agent in an **Administrator** PowerShell:

```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```

Then, in a normal window: `ssh-add $HOME\.ssh\reels_oci`.
