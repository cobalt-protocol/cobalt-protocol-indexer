#!/bin/sh
# Ensure Kubo API and Gateway listen on all interfaces
# so other containers on the same network can reach them.
ipfs config Addresses.API /ip4/0.0.0.0/tcp/5001
ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8080

# Disable subdomain gateway redirects on localhost so we can access
# http://localhost:8082/ipfs/<CID> without timing out on *.ipfs.localhost
ipfs config --json Gateway.PublicGateways '{"localhost": {"UseSubdomains": false, "Paths": ["/ipfs", "/ipns"]}}'
