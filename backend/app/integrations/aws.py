from app.integrations.base import AccountRecord, CheckResult, Connector, ConnectorError, Field, TestDef


class AWSConnector(Connector):
    provider = "aws"
    name = "Amazon Web Services"
    category = "Cloud"
    description = "Checks root MFA, password policy, CloudTrail, S3 public access, encryption, backups and GuardDuty."
    setup_help = (
        "Create an IAM user (or role) with the AWS managed 'SecurityAudit' read-only policy "
        "and paste its access key. Tag IAM users with 'email' so they can be matched to employees. "
        "Use the region where your production workloads run, e.g. ap-south-1 (Mumbai)."
    )
    fields = [
        Field("region", "Primary region", default="ap-south-1"),
        Field("access_key_id", "Access key ID", secret=True),
        Field("secret_access_key", "Secret access key", secret=True),
    ]
    tests = [
        TestDef("aws.root_mfa", "Root account has MFA enabled", ["ACC-03", "ACC-04"]),
        TestDef("aws.password_policy", "IAM password policy requires 12+ characters", ["ACC-08"]),
        TestDef("aws.cloudtrail", "Multi-region CloudTrail is logging", ["LOG-01"]),
        TestDef("aws.s3_public_access_block", "S3 account-level public access block is on", ["NET-01", "ACC-06"]),
        TestDef("aws.ebs_default_encryption", "EBS encryption by default is on", ["CRY-01"]),
        TestDef("aws.rds_encryption", "All RDS instances are encrypted at rest", ["CRY-01"]),
        TestDef("aws.rds_backups", "RDS automated backups retained 7+ days", ["OPS-06"]),
        TestDef("aws.guardduty", "GuardDuty threat detection is enabled", ["LOG-02"]),
    ]

    provides_accounts = True
    max_users = 300

    def __init__(self, config: dict, secrets: dict, session=None):
        super().__init__(config, secrets)
        self._session = session

    @property
    def session(self):
        if self._session is None:
            import boto3

            self._session = boto3.Session(
                aws_access_key_id=self.secrets.get("access_key_id"),
                aws_secret_access_key=self.secrets.get("secret_access_key"),
                region_name=self.config.get("region") or "ap-south-1",
            )
        return self._session

    def verify(self) -> None:
        try:
            self.session.client("sts").get_caller_identity()
        except Exception as e:  # botocore raises many types
            raise ConnectorError(f"AWS credentials could not be verified: {e}") from e

    def _check(self, key: str, fn) -> CheckResult:
        try:
            return fn()
        except Exception as e:
            return CheckResult(key, "error", f"Check failed: {type(e).__name__}: {e}"[:500])

    def run(self) -> list[CheckResult]:
        self.verify()
        s = self.session
        account_id = s.client("sts").get_caller_identity()["Account"]
        iam = s.client("iam")

        def root_mfa():
            on = iam.get_account_summary()["SummaryMap"].get("AccountMFAEnabled") == 1
            return CheckResult("aws.root_mfa", "pass" if on else "fail",
                               "Root MFA enabled" if on else "Root account has no MFA")

        def password_policy():
            try:
                p = iam.get_account_password_policy()["PasswordPolicy"]
            except iam.exceptions.NoSuchEntityException:
                return CheckResult("aws.password_policy", "fail", "No IAM password policy set")
            length = p.get("MinimumPasswordLength", 0)
            return CheckResult("aws.password_policy", "pass" if length >= 12 else "fail",
                               f"Minimum password length is {length}", {"policy": p})

        def cloudtrail():
            ct = s.client("cloudtrail")
            trails = ct.describe_trails()["trailList"]
            logging = [t["Name"] for t in trails if t.get("IsMultiRegionTrail")
                       and ct.get_trail_status(Name=t["TrailARN"]).get("IsLogging")]
            return CheckResult("aws.cloudtrail", "pass" if logging else "fail",
                               f"Logging multi-region trails: {', '.join(logging)}" if logging
                               else "No multi-region CloudTrail is logging", {"trails": [t["Name"] for t in trails]})

        def s3_block():
            s3c = s.client("s3control")
            try:
                cfg = s3c.get_public_access_block(AccountId=account_id)["PublicAccessBlockConfiguration"]
            except s3c.exceptions.NoSuchPublicAccessBlockConfiguration:
                return CheckResult("aws.s3_public_access_block", "fail", "Account-level public access block not set")
            on = all(cfg.values())
            return CheckResult("aws.s3_public_access_block", "pass" if on else "fail",
                               "All four public access block settings on" if on else "Some settings are off",
                               {"configuration": cfg})

        def ebs():
            on = s.client("ec2").get_ebs_encryption_by_default()["EbsEncryptionByDefault"]
            return CheckResult("aws.ebs_default_encryption", "pass" if on else "fail",
                               "EBS default encryption on" if on else "EBS default encryption off")

        rds_instances: list[dict] = []

        def rds_list():
            if not rds_instances:
                for page in s.client("rds").get_paginator("describe_db_instances").paginate():
                    rds_instances.extend(page["DBInstances"])
            return rds_instances

        def rds_enc():
            bad = [d["DBInstanceIdentifier"] for d in rds_list() if not d.get("StorageEncrypted")]
            return CheckResult("aws.rds_encryption", "fail" if bad else "pass",
                               f"{len(bad)} unencrypted RDS instances" if bad
                               else f"All {len(rds_list())} RDS instances encrypted", {"unencrypted": bad})

        def rds_backup():
            bad = [d["DBInstanceIdentifier"] for d in rds_list() if d.get("BackupRetentionPeriod", 0) < 7]
            return CheckResult("aws.rds_backups", "fail" if bad else "pass",
                               f"{len(bad)} RDS instances keep backups under 7 days" if bad
                               else f"All {len(rds_list())} RDS instances keep 7+ days of backups", {"short": bad})

        def guardduty():
            gd = s.client("guardduty")
            ids = gd.list_detectors()["DetectorIds"]
            on = any(gd.get_detector(DetectorId=i)["Status"] == "ENABLED" for i in ids)
            return CheckResult("aws.guardduty", "pass" if on else "fail",
                               "GuardDuty enabled" if on else "GuardDuty not enabled in the primary region")

        checks = [("aws.root_mfa", root_mfa), ("aws.password_policy", password_policy),
                  ("aws.cloudtrail", cloudtrail), ("aws.s3_public_access_block", s3_block),
                  ("aws.ebs_default_encryption", ebs), ("aws.rds_encryption", rds_enc),
                  ("aws.rds_backups", rds_backup), ("aws.guardduty", guardduty)]
        return [self._check(k, fn) for k, fn in checks]

    def list_accounts(self) -> list[AccountRecord]:
        iam = self.session.client("iam")
        out = []
        for page in iam.get_paginator("list_users").paginate():
            for u in page["Users"]:
                if len(out) >= self.max_users:
                    return out
                name = u["UserName"]
                tags = {t["Key"].lower(): t["Value"] for t in iam.list_user_tags(UserName=name).get("Tags", [])}
                policies = {p["PolicyName"] for p in iam.list_attached_user_policies(UserName=name)["AttachedPolicies"]}
                for g in iam.list_groups_for_user(UserName=name)["Groups"]:
                    policies |= {p["PolicyName"] for p in
                                 iam.list_attached_group_policies(GroupName=g["GroupName"])["AttachedPolicies"]}
                out.append(AccountRecord(
                    external_id=u["UserId"], email=tags.get("email", "").lower(), name=name,
                    is_admin="AdministratorAccess" in policies, is_active=True,
                    mfa_enabled=bool(iam.list_mfa_devices(UserName=name)["MFADevices"]),
                    last_login_at=u.get("PasswordLastUsed"),
                ))
        return out
