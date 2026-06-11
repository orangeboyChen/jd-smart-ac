# Disclaimer / 免责声明

[English](#english) | [简体中文](#简体中文)

---

## English

This project (`ha-jd-smart`) is an **unofficial**, community-maintained Home
Assistant custom integration. It is **not affiliated with, endorsed by,
sponsored by, or in any way officially connected to** JD.com, JD Smart
(京东小家), JD Xiaojia, Home Assistant, or any of their subsidiaries or
affiliates. All product names, trademarks, and registered trademarks mentioned
in this repository are the property of their respective owners.

### Purpose

This integration is provided **for personal study, research, and
interoperability** purposes only, so that users who already own air conditioners
controlled through the JD Smart / JD Xiaojia app can integrate those devices
into their own Home Assistant installations.

### No Credentials, No Data Collection

- This repository **does not** ship any JD account credentials, tokens,
  cookies, or personal data.
- All authentication values (such as `cookie`, `tgt`, `pin`, `device_id`,
  `sgm_context`) must be obtained by the user from their **own** logged-in
  session and are stored **only on the user's local Home Assistant instance**.
- The integration communicates **directly** between the user's Home Assistant
  and JD's servers. The maintainers of this repository do not operate any
  intermediate server and do not collect, log, or transmit any user data.

### Use At Your Own Risk

- The integration depends on private, undocumented HTTP APIs used by the
  JD Smart / JD Xiaojia mobile app. These APIs may change, break, be
  rate-limited, or be revoked at any time without notice.
- Using this integration **may violate the JD Smart / JD Xiaojia Terms of
  Service or User Agreement**. You are solely responsible for reviewing and
  complying with the applicable terms before using this software. The
  maintainers accept no responsibility for any account suspension, device
  lockout, data loss, financial loss, legal liability, or other consequence
  resulting from your use of this integration.
- The software is provided **"AS IS", without warranty of any kind**, express
  or implied, including but not limited to the warranties of merchantability,
  fitness for a particular purpose, and non-infringement.

### License & Commercial Support

This project is released under the MIT License (see `LICENSE`). The maintainer
provides this software for personal use, **without any warranty and without
any commercial support**. If you choose to use it in a commercial context,
you do so entirely at your own risk and remain solely responsible for
complying with the JD Smart / JD Xiaojia Terms of Service and any other
applicable laws or third-party rights.

### Takedown

If you are a rights holder and believe this repository infringes on your
rights, please open an issue or contact the maintainer; the relevant content
will be promptly reviewed and, if appropriate, removed.

---

## 简体中文

本项目（`ha-jd-smart`）是一个**非官方**、由社区维护的 Home Assistant 自定义集成。
它与京东（JD.com）、京东小家、Home Assistant 及其任何子公司或关联方**没有任何隶属、
背书、赞助或官方合作关系**。仓库中提及的所有产品名称、商标及注册商标，均为其
各自所有者的财产。

### 用途

本集成**仅供个人学习、研究及互操作性目的使用**，方便已经拥有通过京东小家 App
控制的空调的用户，将设备接入自有的 Home Assistant 实例。

### 不包含凭据，不收集数据

- 仓库中**不包含**任何京东账号凭据、token、Cookie 或个人数据。
- 所有鉴权信息（如 `cookie`、`tgt`、`pin`、`device_id`、`sgm_context` 等）
  必须由用户从**自己**已登录的会话中获取，并**仅保存在用户本地的 Home Assistant
  实例中**。
- 集成由用户的 Home Assistant 与京东服务器**直接通信**。仓库维护者不运营任何
  中间服务器，也不收集、记录或转发用户数据。

### 使用风险自负

- 本集成依赖京东小家 App 所使用的非公开、无文档的 HTTP 接口。这些接口可能在任何
  时间发生变更、失效、被限流或被撤回，恕不另行通知。
- 使用本集成**可能违反京东小家的服务条款或用户协议**。在使用本软件之前，您有责任
  自行审阅并遵守相关条款。维护者对因使用本集成而导致的账号封禁、设备锁定、数据
  丢失、经济损失、法律责任或其他任何后果，**概不负责**。
- 本软件**按"原样"提供，不附带任何明示或默示的担保**，包括但不限于适销性、特定
  用途适用性以及非侵权的担保。

### 协议与商业支持

本项目以 MIT 协议发布（详见 `LICENSE`）。维护者仅以个人身份提供本软件，**不附带
任何担保，也不提供任何形式的商业支持**。如您选择将其用于商业场景，由此产生的全部
风险由您自行承担，您仍需自行遵守京东小家的服务条款，以及其他适用的法律法规和
第三方权利。

### 侵权处理

如您是权利人，且认为本仓库侵犯了您的合法权益，请提交 issue 或联系维护者，相关内容
将被及时审查，并在必要时移除。
