import requests
import json
import datetime
import csv
from azure.identity import DefaultAzureCredential
from rich import print as rprint
from rich.console import Console
from rich.table import Table

# -----------------------------
# API Configuration
# -----------------------------
subscription_id = 'YOUR_SUBSCRIPTION'
resource_url = 'https://management.azure.com/'
api_version_vm   = '2022-03-01'   # Native VMs
api_version_arc  = '2022-03-10'   # Azure Arc Machines
api_version_metrics  = '2018-01-01'  # Metrics endpoint
api_version_insights = '2018-11-27-preview'  # VM Insights
api_version_network = '2023-05-01'  # For network resources

# Metrics we'll collect
# (you can add/remove here)
METRICS_TO_COLLECT = [
    "Transactions", 
    "Ingress", 
    "Egress", 
    "UsedCapacity",
    "SuccessServerLatency",
    "SuccessE2ELatency",
    "Availability"
]

# Aggregations we'll request
AGGREGATIONS = ["Total","Average","Minimum","Maximum"]

# -----------------------------
# Authentication
# -----------------------------
def get_token():
    """
    Gets the access token using DefaultAzureCredential.
    Make sure you've done 'az login' previously or
    configured environment variables (AZURE_CLIENT_ID, etc).
    """
    credential = DefaultAzureCredential()
    token = credential.get_token("https://management.azure.com/.default")
    return token.token

# -----------------------------
# Storage Accounts Collection
# -----------------------------
def get_storage_accounts(subscription_id):
    """
    Collects all Storage Accounts from the subscription.
    """
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{resource_url}subscriptions/{subscription_id}/providers/Microsoft.Storage/storageAccounts?api-version=2021-09-01"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("value", [])

# -----------------------------
# Metric Definitions
# -----------------------------
def get_storage_account_metric_definitions(resource_id, token):
    """
    Returns available metric definitions (name, displayName, etc.)
    for the specified Storage Account.
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{resource_url}{resource_id}/providers/microsoft.insights/metricDefinitions?api-version={api_version_metrics}"
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    return data.get("value", [])

# -----------------------------
# Metrics Collection
# -----------------------------
def get_storage_account_metrics(storage_account, token, timespan):
    """
    Collects metrics for a Storage Account during the specified interval.
    """
    resource_id = storage_account.get("id")
    if not resource_id:
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    metrics = {}
    
    # Request 1: Metrics that don't support dimensions
    url_capacity = (
        f"{resource_url}{resource_id}/providers/microsoft.insights/metrics"
        f"?api-version={api_version_metrics}"
        f"&timespan=P1D"
        f"&interval=PT1H"
        f"&metricnamespace=Microsoft.Storage/storageAccounts"
        f"&metricnames=UsedCapacity"
        f"&aggregation=Average"
    )
    
    # Request 2: Metrics that support dimensions
    url_metrics = (
        f"{resource_url}{resource_id}/providers/microsoft.insights/metrics"
        f"?api-version={api_version_metrics}"
        f"&timespan=P1D"
        f"&interval=PT1H"
        f"&metricnamespace=Microsoft.Storage/storageAccounts"
        f"&metricnames=Transactions,Ingress,Egress,SuccessE2ELatency,SuccessServerLatency,Availability"
        f"&aggregation=Total,Average"
        f"&$filter=GeoType eq 'Primary'"
    )
    
    # Collect UsedCapacity
    response_capacity = requests.get(url_capacity, headers=headers)
    if response_capacity.ok:
        data = response_capacity.json()
        for metric in data.get("value", []):
            mname = metric.get("name", {}).get("value", "").lower()
            timeseries = metric.get("timeseries", [])
            if timeseries and "data" in timeseries[0]:
                datapoints = timeseries[0]["data"]
                if mname == "usedcapacity":
                    values = [point.get("average", 0) for point in datapoints if point.get("average") is not None]
                    metrics["UsedCapacity"] = sum(values) / len(values) if values else 0
    
    # Collect other metrics
    response_metrics = requests.get(url_metrics, headers=headers)
    if response_metrics.ok:
        data = response_metrics.json()
        for metric in data.get("value", []):
            mname = metric.get("name", {}).get("value", "").lower()
            timeseries = metric.get("timeseries", [])
            if timeseries and "data" in timeseries[0]:
                datapoints = timeseries[0]["data"]
                
                if mname == "transactions":
                    total = sum(point.get("total", 0) for point in datapoints if point.get("total") is not None)
                    metrics["Transactions"] = total
                elif mname in ["ingress", "egress"]:
                    total = sum(point.get("total", 0) for point in datapoints if point.get("total") is not None)
                    metrics[mname.capitalize()] = total
                elif mname == "successe2elatency":
                    values = [point.get("average", 0) for point in datapoints if point.get("average") is not None]
                    metrics["SuccessE2ELatency"] = sum(values) / len(values) if values else 0
                elif mname == "successserverlatency":
                    values = [point.get("average", 0) for point in datapoints if point.get("average") is not None]
                    metrics["SuccessServerLatency"] = sum(values) / len(values) if values else 0
                elif mname == "availability":
                    values = [point.get("average", 0) for point in datapoints if point.get("average") is not None]
                    metrics["Availability"] = sum(values) / len(values) if values else 0
    
    return metrics

# -----------------------------
# VM Functions
# -----------------------------
def get_vms(subscription_id, token):
    """Retrieves native VMs from the subscription."""
    url = f"{resource_url}subscriptions/{subscription_id}/providers/Microsoft.Compute/virtualMachines?api-version={api_version_vm}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])

def get_arc_machines(subscription_id, token):
    """Retrieves machines connected via Azure Arc."""
    url = f"{resource_url}subscriptions/{subscription_id}/providers/Microsoft.HybridCompute/machines?api-version={api_version_arc}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])

def get_vm_power_state(resource_id, token, vm_type):
    """Checks the power state of the VM."""
    headers = {"Authorization": f"Bearer {token}"}
    
    if vm_type == "Compute":
        url = f"{resource_url}{resource_id}/instanceView?api-version={api_version_vm}"
    else:
        url = f"{resource_url}{resource_id}/instanceView?api-version={api_version_arc}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if vm_type == "Compute":
                for status in data.get("statuses", []):
                    code = status.get("code", "").lower()
                    if "powerstate" in code:
                        return "running" if "running" in code else "stopped"
            else:
                status = data.get("status", {}).get("status", "").lower()
                return "running" if status == "connected" else "stopped"
        return "unknown"
    except Exception as e:
        print(f"Error checking power state: {str(e)}")
        return "unknown"

def get_vm_insights_status(resource_id, token, vm_type):
    """Checks the VM Insights status."""
    headers = {"Authorization": f"Bearer {token}"}
    api_version = api_version_vm if vm_type == "Compute" else api_version_arc
    
    try:
        # Check extensions
        url = f"{resource_url}{resource_id}/extensions?api-version={api_version}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            extensions = response.json().get("value", [])
            for ext in extensions:
                ext_name = ext.get("name", "").lower()
                if "azuremonitor" in ext_name and "agent" in ext_name:
                    if ext.get("properties", {}).get("provisioningState") == "Succeeded":
                        return "Enabled"
        
        # Check DCRs
        dcr_url = f"{resource_url}{resource_id}/providers/Microsoft.Insights/dataCollectionRuleAssociations?api-version=2021-09-01-preview"
        response = requests.get(dcr_url, headers=headers)
        if response.status_code == 200:
            if response.json().get("value", []):
                return "Enabled"
        
        return "Not enabled"
    except Exception as e:
        print(f"Error checking VM Insights: {str(e)}")
        return "Unknown"

def get_vm_metrics(token):
    """Collects metrics from all VMs (native and Arc)."""
    vm_metrics = {
        'total_machines': 0,
        'total_monitored': 0,
        'resource_groups': {}
    }

    # Process native VMs
    compute_vms = get_vms(subscription_id, token)
    for vm in compute_vms:
        process_vm(vm, "Compute", token, vm_metrics)

    # Process Arc machines
    arc_machines = get_arc_machines(subscription_id, token)
    for machine in arc_machines:
        process_vm(machine, "Arc", token, vm_metrics)

    return vm_metrics

def process_vm(vm, vm_type, token, vm_metrics):
    """Processes an individual VM and adds its metrics to the dictionary."""
    vm_name = vm.get("name", "Unnamed")
    resource_id = vm.get("id", "")
    rg_name = resource_id.split('/')[4].lower() if resource_id else "unknown"

    # Initialize the resource group if needed
    if rg_name not in vm_metrics['resource_groups']:
        vm_metrics['resource_groups'][rg_name] = {
            'machines': []
        }

    # Collect metrics
    power_state = get_vm_power_state(resource_id, token, vm_type)
    insights_status = get_vm_insights_status(resource_id, token, vm_type)

    # Add the machine to the resource group
    vm_metrics['resource_groups'][rg_name]['machines'].append({
        'name': vm_name,
        'type': vm_type,
        'power_state': power_state,
        'monitored': insights_status == "Enabled",
        'insights_status': insights_status
    })

    # Update counters
    vm_metrics['total_machines'] += 1
    if insights_status == "Enabled":
        vm_metrics['total_monitored'] += 1

# -----------------------------
# Network Resources Collection
# -----------------------------
def get_network_resources(subscription_id, token):
    """Collects all network resources."""
    network_metrics = {
        'er_vpn_connections': {'count': 0, 'items': []},
        'expressroute_circuits': {'count': 0, 'items': []},
        'express_route_gateways': {'count': 0, 'items': []},
        'network_interfaces': {'count': 0, 'items': []},
        'network_security_groups': {'count': 0, 'items': []},
        'network_virtual_appliances': {'count': 0, 'items': []},
        'private_endpoints': {'count': 0, 'items': []},
        'public_ips': {'count': 0, 'items': []},
        'route_tables': {'count': 0, 'items': []},
        'virtual_network_gateways': {'count': 0, 'items': []},
        'virtual_networks': {'count': 0, 'items': []}
    }

    headers = {"Authorization": f"Bearer {token}"}
    
    # Resource mapping and their APIs
    resources = {
        'virtual_networks': '/providers/Microsoft.Network/virtualNetworks',
        'network_interfaces': '/providers/Microsoft.Network/networkInterfaces',
        'network_security_groups': '/providers/Microsoft.Network/networkSecurityGroups',
        'public_ips': '/providers/Microsoft.Network/publicIPAddresses',
        'route_tables': '/providers/Microsoft.Network/routeTables',
        'private_endpoints': '/providers/Microsoft.Network/privateEndpoints',
        'expressroute_circuits': '/providers/Microsoft.Network/expressRouteCircuits',
        'virtual_network_gateways': '/providers/Microsoft.Network/virtualNetworkGateways',
        'er_vpn_connections': '/providers/Microsoft.Network/connections',
        'express_route_gateways': '/providers/Microsoft.Network/expressRouteGateways',
        'network_virtual_appliances': '/providers/Microsoft.Network/networkVirtualAppliances'
    }

    for resource_type, resource_path in resources.items():
        url = f"{resource_url}subscriptions/{subscription_id}{resource_path}?api-version={api_version_network}"
        try:
            response = requests.get(url, headers=headers)
            if response.ok:
                data = response.json()
                items = data.get('value', [])
                network_metrics[resource_type]['count'] = len(items)
                
                for item in items:
                    resource_info = {
                        'name': item.get('name'),
                        'resource_group': item.get('id', '').split('/')[4],
                        'provisioning_state': item.get('properties', {}).get('provisioningState', 'Unknown'),
                        'health_state': get_resource_health(item.get('id'), token)
                    }
                    network_metrics[resource_type]['items'].append(resource_info)
            else:
                print(f"Error collecting {resource_type}: {response.status_code}")
        except Exception as e:
            print(f"Error processing {resource_type}: {str(e)}")

    return network_metrics

def get_resource_health(resource_id, token):
    """Checks the health state of the resource."""
    if not resource_id:
        return "Unknown"
        
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{resource_url}{resource_id}/providers/Microsoft.ResourceHealth/availabilityStatuses/current?api-version=2022-10-01"
    
    try:
        response = requests.get(url, headers=headers)
        if response.ok:
            data = response.json()
            return data.get('properties', {}).get('availabilityState', 'Unknown')
        return "Unknown"
    except:
        return "Unknown"

# -----------------------------
# MAIN
# -----------------------------
def main():
    token = get_token()

    # Collect Storage Account metrics
    print(f"\nCollecting Storage Accounts from subscription: {subscription_id}")
    storage_accounts = get_storage_accounts(subscription_id)
    print(f"Total Storage Accounts found: {len(storage_accounts)}")

    metrics_results = []
    for sa in storage_accounts:
        sa_name = sa.get("name", "N/A")
        print(f"Collecting metrics for Storage Account: {sa_name}")
        sa_metrics = get_storage_account_metrics(sa, token, None)
        metrics_results.append({
            "storage_account": sa_name,
            "resource_group": sa.get("id", "").split("/")[4] if "id" in sa else "N/A",
            "metrics": sa_metrics
        })

    # Collect VM metrics
    print("\nProcessing VMs and Arc machines...")
    vm_metrics = get_vm_metrics(token)

    # Collect network metrics
    print("\nProcessing network resources...")
    network_metrics = get_network_resources(subscription_id, token)

    # Display tables and export to CSV
    display_tables(metrics_results, vm_metrics, network_metrics)
    export_to_csv(metrics_results, vm_metrics, network_metrics)

def export_to_csv(metrics_results, vm_metrics_results=None, network_metrics=None):
    """
    Exports results to CSV
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Storage Accounts
    if metrics_results:
        filename = f"storage_metrics_{timestamp}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Storage Account', 'Resource Group', 'Transactions', 
                'Ingress (Bytes)', 'Egress (Bytes)', 'Used Capacity (Bytes)',
                'E2E Latency (ms)', 'Server Latency (ms)', 'Availability (%)'
            ])
            
            for result in metrics_results:
                metrics = result.get('metrics', {}) or {}
                writer.writerow([
                    result.get('storage_account'),
                    result.get('resource_group'),
                    metrics.get('Transactions', 'N/A'),
                    metrics.get('Ingress', 'N/A'),
                    metrics.get('Egress', 'N/A'),
                    metrics.get('UsedCapacity', 'N/A'),
                    metrics.get('SuccessE2ELatency', 'N/A'),
                    metrics.get('SuccessServerLatency', 'N/A'),
                    metrics.get('Availability', 'N/A')
                ])
        print(f"\nStorage Account metrics exported to: {filename}")

    # VMs
    if vm_metrics_results:
        filename = f"vm_metrics_{timestamp}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'VM Name', 'Resource Group', 'Type', 'Power State',
                'Monitored', 'Insights Status'
            ])
            
            for rg, data in vm_metrics_results['resource_groups'].items():
                for machine in data['machines']:
                    writer.writerow([
                        machine['name'],
                        rg,
                        machine['type'],
                        machine['power_state'],
                        'Yes' if machine['monitored'] else 'No',
                        machine['insights_status']
                    ])
        print(f"VM metrics exported to: {filename}")

    # Network Resources
    if network_metrics:
        filename = f"network_metrics_{timestamp}.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Resource Type', 'Resource Name', 'Resource Group',
                'Provisioning State', 'Health State'
            ])
            
            for resource_type, data in network_metrics.items():
                for item in data['items']:
                    writer.writerow([
                        resource_type.replace('_', ' ').title(),
                        item['name'],
                        item['resource_group'],
                        item['provisioning_state'],
                        item['health_state']
                    ])
        print(f"Network metrics exported to: {filename}")

def display_tables(storage_metrics, vm_metrics, network_metrics):
    """Displays metrics tables."""
    console = Console()

    # Storage Accounts Table
    if storage_metrics:
        table = Table(
            title="Storage Account Metrics (Last 24h)",
            width=160,
            show_lines=True
        )
        
        table.add_column("Storage Account", style="bold", width=20)
        table.add_column("RG", width=15)
        table.add_column("Trans", justify="right", width=10)
        table.add_column("Ingress", justify="right", width=12)
        table.add_column("Egress", justify="right", width=12)
        table.add_column("Used Cap", justify="right", width=12)
        table.add_column("E2E Lat", justify="right", width=10)
        table.add_column("Srv Lat", justify="right", width=10)
        table.add_column("Avail%", justify="right", width=8)

        def format_bytes(bytes_val):
            if isinstance(bytes_val, (int, float)):
                for unit in ['', 'KB', 'MB', 'GB', 'TB']:
                    if bytes_val < 1024.0:
                        return f"{bytes_val:.2f} {unit}"
                    bytes_val /= 1024.0
            return "N/A"

        def format_number(val, decimal_places=2):
            if isinstance(val, (int, float)):
                return f"{val:,.{decimal_places}f}"
            return "N/A"

        for result in storage_metrics:
            metrics = result.get('metrics', {}) or {}
            table.add_row(
                result.get('storage_account'),
                result.get('resource_group'),
                format_number(metrics.get('Transactions'), 0),
                format_bytes(metrics.get('Ingress')),
                format_bytes(metrics.get('Egress')),
                format_bytes(metrics.get('UsedCapacity')),
                format_number(metrics.get('SuccessE2ELatency'), 2),
                format_number(metrics.get('SuccessServerLatency'), 2),
                format_number(metrics.get('Availability'), 3)
            )

        console.print("\n")
        console.print(table)

    # VMs Table
    if vm_metrics:
        table = Table(
            title="Virtual Machines Monitoring Status",
            width=120,
            show_lines=True
        )
        
        table.add_column("VM Name", style="bold", width=25)
        table.add_column("RG", width=20)
        table.add_column("Type", width=10)
        table.add_column("Power", width=10)
        table.add_column("Monitored", width=10)
        table.add_column("Status", width=30)

        for rg, data in vm_metrics['resource_groups'].items():
            for machine in data['machines']:
                table.add_row(
                    machine['name'],
                    rg,
                    machine['type'],
                    machine['power_state'],
                    "✓" if machine['monitored'] else "✗",
                    machine['insights_status']
                )

        console.print("\n")
        console.print(table)
        console.print(f"\nTotal VMs: {vm_metrics['total_machines']}")
        console.print(f"Monitored: {vm_metrics['total_monitored']}")
        console.print(f"Not Monitored: {vm_metrics['total_machines'] - vm_metrics['total_monitored']}")

    # Network Resources Table
    if network_metrics:
        table = Table(
            title="Network Resources Status",
            width=120,
            show_lines=True
        )
        
        table.add_column("Resource Type", style="bold", width=30)
        table.add_column("Count", justify="right", width=10)
        table.add_column("Available", justify="right", width=10)
        table.add_column("Degraded", justify="right", width=10)
        table.add_column("Unavailable", justify="right", width=10)

        for resource_type, data in network_metrics.items():
            available = sum(1 for item in data['items'] if item['health_state'].lower() == 'available')
            degraded = sum(1 for item in data['items'] if item['health_state'].lower() == 'degraded')
            unavailable = sum(1 for item in data['items'] if item['health_state'].lower() == 'unavailable')
            
            table.add_row(
                resource_type.replace('_', ' ').title(),
                str(data['count']),
                str(available),
                str(degraded),
                str(unavailable)
            )

        console.print("\n")
        console.print(table)

if __name__ == '__main__':
    main()
