CREATE DATABASE IF NOT EXISTS flamepaybot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE flamepaybot;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tg_user_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255) NULL,
    full_name VARCHAR(255) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 0,
    is_banned TINYINT(1) NOT NULL DEFAULT 0,
    balance_available DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    balance_hold DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    activated_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_codes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    max_uses INT NOT NULL DEFAULT 1,
    used_count INT NOT NULL DEFAULT 0,
    expires_at DATETIME NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_by BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gateway_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    way_code VARCHAR(50) NOT NULL UNIQUE,
    title VARCHAR(100) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gateway_packages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    gateway_id BIGINT NOT NULL,
    label VARCHAR(100) NOT NULL,
    amount_cents INT NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_packages_gateway FOREIGN KEY (gateway_id) REFERENCES gateway_configs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    mch_no VARCHAR(32) NOT NULL,
    mch_order_no VARCHAR(64) NOT NULL UNIQUE,
    pay_order_no VARCHAR(64) NULL,
    way_code VARCHAR(50) NOT NULL,
    package_label VARCHAR(100) NOT NULL,
    amount_cents INT NOT NULL,
    fee_percent DECIMAL(5,2) NOT NULL,
    final_amount_cents INT NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    status ENUM('0','1','2','3','4','5','6') NOT NULL DEFAULT '0',
    cashier_url TEXT NULL,
    provider_raw_create TEXT NULL,
    provider_raw_notify TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_orders_pay_order_no (pay_order_no),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS payout_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    network ENUM('TRC20','BEP20') NOT NULL,
    address VARCHAR(255) NOT NULL,
    status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    admin_note VARCHAR(255) NULL,
    txid VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payout_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS balance_ledger (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    entry_type ENUM('deposit_credit','payout_hold','payout_approve','payout_reject_return') NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    ref_order_id BIGINT NULL,
    ref_payout_id BIGINT NULL,
    note VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ledger_user_time (user_id, created_at),
    CONSTRAINT fk_ledger_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_ledger_order FOREIGN KEY (ref_order_id) REFERENCES orders(id),
    CONSTRAINT fk_ledger_payout FOREIGN KEY (ref_payout_id) REFERENCES payout_requests(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_tg_user_id BIGINT NULL,
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(64) NULL,
    target_id VARCHAR(64) NULL,
    detail_json TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_actor (actor_tg_user_id)
);

CREATE TABLE IF NOT EXISTS callback_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_key VARCHAR(128) NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    processed TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS gateways (
  code VARCHAR(32) PRIMARY KEY,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
