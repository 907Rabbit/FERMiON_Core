# Offline Nmap/NSE Report Analysis

FERMiON's `nmap_reports` application is an offline XML parser for reports a
user has already created. It has no Nmap binary, network socket, shell, packet,
or scan capability.

Place an Nmap XML report in the control-plane runtime directory
`nmap-reports` and request either `analyze_report` or `compare_reports`.
The adapter accepts only `.xml` files up to 25 MiB, rejects DTD/entity
declarations, and treats every host, port, service, and NSE-script output value
as untrusted data.

`analyze_report` returns host status, open ports, services, script IDs, and
bounded script output. `compare_reports` reports new/closed open ports and new
script IDs between two supplied reports. Neither operation can launch an Nmap
or NSE scan.
