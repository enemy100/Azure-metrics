# Azure-metrics KQL Queries

Vulnerabilities on Servers

SecurityResources
| where type == "microsoft.security/assessments/subassessments" and properties.additionalData.assessedResourceType == "ServerVulnerability" or properties.additionalData.assessedResourceType == "ServerVulnerabilityTvm"  and properties.status.code == "Unhealthy"
| extend Vulnerability=properties.displayName,
    Description=properties.description,
    Severity=properties.status.severity,
    Threat=properties.additionalData.threat,
    Impact=properties.impact,
    Fix=properties.remediation,
    VulnId=properties.id,
    Date=format_datetime(todatetime(properties.timeGenerated),'yyyy-MM-dd'),
    UUID=name,
    VM=split(id,'/')[8]
| project UUID,VM,Vulnerability,Date,Severity,Description,Threat,Impact,Fix,VulnId
