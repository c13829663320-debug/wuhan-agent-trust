# 江城验真可下载材料

- [skills.xlsx](skills.xlsx)：12项技能清单，以及4个工具岗位和8条运行规则。包含输入、输出、触发时段、服务对象、量化验收标准和验证说明。
- [skills.csv](skills.csv)：同一份技能明细，UTF-8 BOM编码，便于导入表格工具。
- [catalog.json](catalog.json)：应用使用的原始能力目录。
- [receipt-schema.json](receipt-schema.json)：回执结构约定；完整验收仍由 `/api/verify` 重放执行。

清单按实际实现组织，不用八行业条目凑数量。工具岗位没有连接大模型，均由用户操作触发，没有安装定时上班任务。运行产生的真实证据在页面下载；合成健康／过期／缺回执示例不会进入真实观测账本。

部署目标为 <https://wutiantian.cn/agent-trust/>，当前材料制作时部署待核验。功能与范围详见项目根目录的 README。


## 独立交付

网页页脚提供本项目的可编辑 PPT、PDF、使用说明和独立源码下载。源码包排除运行数据库、部署凭据和其他项目内容；在干净目录执行 `npm ci` 后可单独构建。修改后先运行 `python3 scripts/package-source.py` 更新源码下载包，再运行 `npm run build`。
