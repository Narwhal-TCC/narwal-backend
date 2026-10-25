# Edge routing is configured on the EC2 instance (Nginx :80 → /var/www/narwal, /api/* → 127.0.0.1:8080).
# See user_data in ec2.tf. This file anchors the infra contract for the single-origin pattern.
