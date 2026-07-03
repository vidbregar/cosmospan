package bandwidth

import (
	"context"
	"fmt"
	"log"
	"strconv"
	"strings"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
)

type State struct {
	IngressCap float64
	EgressCap  float64

	TotalIngressReqs float64
	TotalEgressReqs  float64
}

func initIngressCap(bandwidthSnapshot map[string]*State, nodeName string, ingress float64) {
	_, exists := bandwidthSnapshot[nodeName]
	if !exists {
		bandwidthSnapshot[nodeName] = &State{}
	}

	bandwidthSnapshot[nodeName].IngressCap = ingress
}

func initEgressCap(bandwidthSnapshot map[string]*State, nodeName string, egress float64) {
	_, exists := bandwidthSnapshot[nodeName]
	if !exists {
		bandwidthSnapshot[nodeName] = &State{}
	}

	bandwidthSnapshot[nodeName].EgressCap = egress
}

func SnapshotBandwidths(k8sClient *kubernetes.Clientset) map[string]*State {
	bandwidthsSnapshot := make(map[string]*State)

	nodes, err := k8sClient.CoreV1().Nodes().List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		log.Fatalf("Error listing nodes: %s", err.Error())
	}

	for _, node := range nodes.Items {
		nodeName := node.Name
		ingressStr, ok := node.Labels["example.com/ingress-bandwidth-Mbps"]
		if ok && ingressStr != "" {
			ingress, err := strconv.ParseFloat(strings.TrimSpace(ingressStr), 64)
			if err != nil {
				klog.V(5).ErrorS(err, "error converting string to float")
				panic(err)
			}

			initIngressCap(bandwidthsSnapshot, nodeName, ingress)
		} else {
			initIngressCap(bandwidthsSnapshot, nodeName, 0)
		}

		egressStr, ok := node.Labels["example.com/egress-bandwidth-Mbps"]
		if ok && egressStr != "" {
			egress, err := strconv.ParseFloat(strings.TrimSpace(egressStr), 64)
			if err != nil {
				klog.V(5).ErrorS(err, "error converting string to float")
				panic(err)
			}

			initEgressCap(bandwidthsSnapshot, nodeName, egress)
		} else {
			initEgressCap(bandwidthsSnapshot, nodeName, 0)
		}

		pods, err := k8sClient.CoreV1().Pods("").List(context.TODO(), metav1.ListOptions{
			FieldSelector: fmt.Sprintf("spec.nodeName=%s", nodeName),
		})
		if err != nil {
			log.Fatalf("Error listing pods for node %s: %s", nodeName, err.Error())
		}

		totalIngressReqs := float64(0)
		totalEgressReqs := float64(0)

		for _, pod := range pods.Items {
			ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
			if ok {
				ingressReq, err := strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
				if err != nil {
					log.Fatalf("Error converting ingress request to float: %s", err.Error())
				}

				totalIngressReqs += ingressReq
			}

			egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
			if ok {
				egressReq, err := strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
				if err != nil {
					log.Fatalf("Error converting egress request to float: %s", err.Error())
				}

				totalEgressReqs += egressReq
			}
		}

		bandwidthsSnapshot[nodeName].TotalIngressReqs = totalIngressReqs
		bandwidthsSnapshot[nodeName].TotalEgressReqs = totalEgressReqs
	}

	return bandwidthsSnapshot
}
