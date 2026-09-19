# Deploy to Azure: quick start

About an hour, start to finish. You end with `https://<name>.<region>.cloudapp.azure.com/`
serving the phone page over HTTPS.

**What you create in Azure:** one **Linux virtual machine**. Not App Service,
Container Apps or Functions. The app needs Docker Compose (the app plus Caddy
for HTTPS), ffmpeg, and one long-running process that keeps jobs in memory.
A plain VM does all of that and is covered by the free account.

**What you need on your PC:** Windows PowerShell (it has `ssh` and `scp`
built in) and this repo.

---

## 1. Azure account (5 min)

1. Sign up at <https://azure.microsoft.com/free>. You get $200 credit for 30
   days and some services free for 12 months.
2. **Within 30 days, upgrade to pay-as-you-go** (portal → *Subscriptions* →
   your subscription → *Upgrade*). If you don't, the subscription is disabled
   when the 30 days end and the VM stops. Upgrading keeps the 12 months of
   free services; you pay only for what is outside them.

## 2. SSH key (2 min, on your PC)

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\reels_vm
Get-Content $HOME\.ssh\reels_vm.pub     # copy this whole line for step 3
```

Press Enter at the passphrase prompt, or set one.

## 3. Create the VM (10 min)

In the portal search for **Free services** and create the Linux virtual
machine from that page, so free-eligible options are preselected. Then check
each tab:

| Tab | Setting | Value |
|-----|---------|-------|
| Basics | Resource group | new: `reels` |
| Basics | Region | one near your friends |
| Basics | Image | **Ubuntu Server 24.04 LTS - x64 Gen2** |
| Basics | Size | **Standard_B2ats_v2** (if unavailable in the region: `Standard_B1s`) |
| Basics | Authentication | **SSH public key**, username `azureuser`, paste the line from step 2 |
| Basics | Public inbound ports | Allow selected: **SSH (22), HTTP (80), HTTPS (443)** |
| Disks | OS disk type | **Premium SSD (locally-redundant)** |
| Disks | OS disk size | **64 GiB (P6)**. The default 30 GiB is a different, billed size. |
| Monitoring | Boot diagnostics | Disable |
| Management | Auto-shutdown | Off (the site must stay up) |

**Review + create** → **Create**. Wait for "Your deployment is complete".

## 4. Networking (5 min)

1. **DNS name.** Open the VM → *Overview* → next to *DNS name* click
   *Not configured* → set a label such as `myreels` → *Save*. Your address is
   now `myreels.<region>.cloudapp.azure.com`. This is your `SITE_ADDRESS`.
2. **Lock SSH to your IP.** VM → *Networking* → *Network settings* → open the
   network security group → *Inbound security rules* → the SSH rule →
   *Source*: **My IP address** → *Save*. Leave 80 and 443 open to Any.

## 5. Budget alert (2 min)

Portal → *Cost Management* → *Budgets* → *Add*: amount **5** (your
currency), monthly, alert at 80% and 100% to your email. Expect a small
monthly charge for the public IP address (next section); anything well
above that means something is billed that shouldn't be.

## 6. Prepare the VM (10 min)

Connect:

```powershell
ssh -i $HOME\.ssh\reels_vm azureuser@myreels.<region>.cloudapp.azure.com
```

On the VM, add swap (every free size has 1 GiB of RAM) and install Docker:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker azureuser
exit
```

The `exit` matters: the Docker group only applies after you reconnect.

## 7. Copy the code (3 min, on your PC)

The repo has no remote, so send a snapshot of `master` over SSH. From the
repo folder in PowerShell:

```powershell
git archive --format=tar.gz -o reels.tar.gz master
scp -i $HOME\.ssh\reels_vm reels.tar.gz azureuser@myreels.<region>.cloudapp.azure.com:~
ssh -i $HOME\.ssh\reels_vm azureuser@myreels.<region>.cloudapp.azure.com
```

On the VM:

```bash
mkdir -p ~/reels && tar -xzf ~/reels.tar.gz -C ~/reels && cd ~/reels
cp .env.example .env
openssl rand -hex 24          # copy the output: this is your API_KEY
nano .env
```

Set these four lines in `.env` (Ctrl+O, Enter, Ctrl+X to save):

```
API_KEY=<the random value>
WORKERS=1
WEB_PASSCODE=<the passcode you give your friends>
SITE_ADDRESS=myreels.<region>.cloudapp.azure.com
```

## 8. Start it (5 min)

```bash
cd ~/reels
docker compose up -d --build
docker compose logs -f caddy     # wait for "certificate obtained successfully", then Ctrl+C
curl https://myreels.<region>.cloudapp.azure.com/health
```

`/health` should return `"status":"ok"` and `"ffmpeg":true`.

## 9. Check on a phone

1. Open `https://myreels.<region>.cloudapp.azure.com/` and enter the passcode.
2. Paste a TikTok link, wait for the player, tap **Share to WhatsApp**.
3. Android: browser menu → **Add to Home screen**. After that the app shows up
   in TikTok's share menu.
4. Send the address and passcode to your friends.

---

## Updating after code changes

On your PC, repeat the `git archive` and `scp` lines from step 7. On the VM:

```bash
cd ~/reels && tar -xzf ~/reels.tar.gz && docker compose up -d --build
```

Your `.env` is untouched because it isn't in the archive. Rebuilding
restarts the app, which empties the Recent feed.

To pick up a newer `yt-dlp` when downloads start failing, bump it in
`requirements.txt`, then update as above.

## Costs

| Item | Cost |
|------|------|
| VM, B2ats v2 or B1s, one running all month | free for 12 months (750 h/month) |
| OS disk, Premium SSD 64 GiB (P6) | free for 12 months |
| Public IPv4 address (Standard SKU) | **not free**, roughly a few dollars a month |
| Outbound data | free up to the monthly allowance; short clips stay far below it |

After 12 months everything is billed at normal rates. Delete the `reels`
resource group to stop all charges at once.

## When something goes wrong

| Symptom | Check |
|---------|-------|
| Browser says the site can't be reached | Ports 80/443 open in the security group; `docker compose ps` shows both containers up |
| Caddy logs show certificate errors | `SITE_ADDRESS` matches the DNS name exactly; port 80 is open (Let's Encrypt uses it) |
| `/` returns 404 | `WEB_PASSCODE` is empty in `.env`; set it and run `docker compose up -d` |
| Instagram fails with "requires a login" | Add a cookies file: see "Instagram cookies" in the README |
| Downloads fail with "blocked" | The platform is refusing Azure's IP range or yt-dlp is out of date; update `yt-dlp` first |
| Container restarts or jobs time out | `free -h` shows the swap is active; `WORKERS=1` in `.env` |

View app logs with `docker compose logs -f api`.
