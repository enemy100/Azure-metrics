# Azure Metrics Collector

**The script functions as an Azure resource metrics collector that gathers data from:**

  -  Storage Accounts - collects performance metrics including transactions, bandwidth, latency, and capacity
  -  Virtual Machines - both native Azure VMs and Arc-connected machines, checking monitoring status
  -  Network Resources - checks availability and health status of various networking components

*Features*

  -  Authentication using Azure DefaultAzureCredential (supports CLI login, managed identities, etc.)
  -  Collects detailed metrics from Storage Accounts over the last 24 hours
  -  Monitors VM Insights status across both native VMs and Arc-connected machines
  -  Evaluates health state of network resources
  -  Presents results in formatted tables using the Rich library
  -  Exports all metrics to time-stamped CSV files

*Requirements*

  -  Python 3.6+
  -  Required packages: requests, azure-identity, rich
  -  Azure subscription with appropriate permissions
  -  Authenticated Azure CLI session (az login)

*Usage*
Simply run the script after installing the required dependencies:
```
pip install requests azure-identity rich
python azure_metrics_collector.py
```
*Output*
The script generates three types of outputs:

  -  Console tables displaying metrics in a readable format
  -  CSV exports for detailed analysis
  -  Summary statistics for quick assessment



