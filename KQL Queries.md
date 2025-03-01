# Azure KQL Queries

**Vulnerabilities on Servers**
```
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
```

**SQL Vulnerabilities**
```
SecurityResources
| where type == "microsoft.security/assessments/subassessments" and properties.additionalData.assessedResourceType=="SqlServerVulnerability" or properties.additionalData.assessedResourceType=="SqlVirtualMachineVulnerability" and properties.status.severity=="High"  and properties.status.code == "Unhealthy"
| extend vulnerability=properties.displayName,
    description=properties.description,
    severity=properties.status.severity,
    threat=properties.additionalData.threat,
    impact=properties.impact,
    fix=properties.remediation,
    vulnId=properties.id
```

**Get VM and Arc informations**
```
resources
| where type in~ ("microsoft.compute/virtualmachines", "microsoft.hybridcompute/machines")
| extend joinId = tolower(id)
| extend Type = case(
    type =~ "microsoft.compute/virtualmachines", "virtualmachines",
    type =~ "microsoft.hybridcompute/machines", "machines",
    "unknown"
)
| extend OS = case(
    type =~ "microsoft.hybridcompute/machines", 
    tolower(coalesce(tostring(properties.osName), tostring(properties.osType))),
    tolower(tostring(properties.storageProfile.osDisk.osType))
)
| extend Status = case(
    type =~ "microsoft.hybridcompute/machines", 
    properties.status,
    properties.extended.instanceView.powerState.displayStatus
)
| join kind=leftouter (
    patchassessmentresources
    | where type in~ ("microsoft.compute/virtualmachines/patchassessmentresults", "microsoft.hybridcompute/machines/patchassessmentresults")
    | where properties.status =~ "Succeeded" or properties.status =~ "Inprogress"
    | parse id with resourceId "/patchAssessmentResults" *
    | extend joinId = tolower(resourceId)
    | project joinId, assessProperties = properties
) on $left.joinId == $right.joinId
| extend PendingUpdates = case(
    assessProperties.osType =~ "Windows",
    tostring(coalesce(assessProperties.availablePatchCountByClassification.critical, 0) + 
            coalesce(assessProperties.availablePatchCountByClassification.security, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.updateRollup, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.featurePack, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.servicePack, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.definition, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.tools, 0) +
            coalesce(assessProperties.availablePatchCountByClassification.updates, 0)),
    assessProperties.osType =~ "Linux",
    tostring(coalesce(assessProperties.availablePatchCountByClassification.security, 0) + 
            coalesce(assessProperties.availablePatchCountByClassification.other, 0)),
    "0"
)
| extend UpdateStatus = iff(PendingUpdates == "0" or isempty(PendingUpdates), "No pending updates", 
    strcat(PendingUpdates, " updates pending"))
| project
    Name = name,
    Type,
    OS,
    Location = location,
    Status,
    ["Update Status"] = UpdateStatus
| order by Name asc

