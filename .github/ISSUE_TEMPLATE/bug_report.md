---
name: Bug report
about: Something is not working as expected
labels: bug
---

## Description

A clear description of the bug.

## Environment

- kube-seer version: (`helm list -n monitoring`)
- Kubernetes version: (`kubectl version --short`)
- Cluster type: (Kind / EKS / GKE / AKS / other)
- LLM intelligence enabled: yes / no

## Steps to reproduce

1.
2.
3.

## Expected behavior

## Actual behavior

## Logs

```
kubectl logs -n monitoring deploy/kube-seer --tail=100
```

## Additional context
