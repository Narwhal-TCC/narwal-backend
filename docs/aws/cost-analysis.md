# Narwal AWS cost analysis (Learner Lab)

Estimates for **us-east-1**, **on-demand** pricing (order of magnitude). Learner Lab consumes **platform credit** (~$100 per student); treat these numbers as planning guides, not invoices.

**Stack (as provisioned in `infra/`):** CloudFront + S3 (UI + app data) + EC2 API (**t3.medium** default, **30 GiB** root gp3 + separate **data** EBS volume) + EIP + **ECR** + SQLite on EBS (no RDS).

---

## Cost drivers (ranked)

1. **EC2 hours** — dominates if the instance runs 24/7.
2. **EBS** — charged while volume exists (~$2–4/month for 30–40 GiB gp3).
3. **CloudFront + S3** — low at TCC traffic levels.
4. **ECR** — storage ~$0.10/GiB-month for one image (~negligible vs EC2).
5. **Data transfer** — usually small for demos; spikes if large downloads.

**Operating rule:** **Stop the API EC2** when not demoing. CloudFront + S3 still serve the UI; `/api/*` fails until the instance is started again.

---

## Unit rates (reference)

| Service | Assumption | ~USD |
| ------- | ---------- | ---- |
| EC2 **t3.medium** | 2 vCPU, 4 GiB | **~$0.042/hour** (~$30/month if 24/7) |
| EC2 **t3.large** | 2 vCPU, 8 GiB (if resize after OOM) | **~$0.083/hour** (~$61/month if 24/7) |
| EBS gp3 | 30 GiB | **~$2.40/month** |
| S3 Standard | 2 GiB storage + requests | **<$1/month** |
| CloudFront | Low traffic + invalidations | **~$1–5/month** |
| ECR | 1 image ~1–2 GiB compressed layers | **~$0.10–0.25/month** |
| EIP | Associated with instance | **$0**† |

†Charges apply if an EIP is **allocated but not associated**.

---

## Scenario A — Recommended (3-month TCC)

**Goal:** Stay within **~$100 credit** while keeping infra for **~3 months**.

| Item | Assumption | ~USD/month | ~USD/3 months |
| ---- | ---------- | ---------- | ------------- |
| EC2 t3.medium | **30 hours/month** running | $1.3 | $3.9 |
| EC2 t3.medium | **40 hours/month** running | $1.7 | $5.1 |
| EBS 30 GiB | Always on | $2.4 | $7.2 |
| S3 + CloudFront + ECR | Demo traffic | $2–5 | $6–15 |
| **Total (30 h/mo)** | | **~$6–9** | **~$18–27** |
| **Total (40 h/mo)** | | **~$7–10** | **~$21–30** |

Add buffer for data transfer and occasional **t3.large** tests (+~$0.04/h vs medium).

---

## Scenario B — Always-on API (not recommended)

| Item | ~USD/month | ~USD/3 months |
| ---- | ---------- | ------------- |
| EC2 t3.medium 24/7 | ~$30 | ~$90 |
| EC2 t3.large 24/7 | ~$61 | ~$183 |
| EBS + S3 + CF + ECR | ~$5–10 | ~$15–30 |

**24/7 t3.medium for 3 months** can consume most or all of **$100** before counting transfer. **24/7 t3.large exceeds $100.**

---

## Scenario C — Resize to t3.large for demos only

Same as Scenario A but EC2 hours billed at large rate when resized:

| EC2 hours | t3.large cost |
| --------- | ------------- |
| 30 h/month | ~$2.5/month |
| 40 h/month | ~$3.3/month |

Use when **t3.medium** OOMs during model preload or multi-model switching.

---

## ECR vs no ECR

Including **ECR** adds roughly **$0.10–0.50/month** for a single backend repository—**immaterial** compared to EC2. ECR is **locked in** for reproducible GitHub Actions deploys (see spec).

---

## Cost optimization checklist

- [ ] Stop EC2 after each work session (Start Lab → start instance only for deploy/demo).
- [ ] Do not leave unused EIPs disassociated.
- [ ] Use targeted CloudFront invalidations (`/index.html`, `/assets/*`) instead of full `/*` when possible.
- [ ] Keep model artifacts in S3 (not duplicated on large EBS).
- [ ] Snapshot SQLite to S3 occasionally instead of oversized EBS.

---

## Report wording (suggested)

> Infrastructure is sized for **intermittent demo use** (~30–40 EC2 hours per month) to preserve AWS Academy credit over three months. Continuous production operation would require a larger budget or a smaller instance with reduced model concurrency; the architecture document describes RAM limits and resize to **t3.large** if needed.

---

## Traceability

Supports requirements **DEPLOY-13**, **DEPLOY-15** (cost and instance sizing documentation).
