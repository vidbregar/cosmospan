package uptime

import (
	"context"
	"github.com/vidbregar/federation-descheduler/pkg/plugins"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
	"log"
	"strconv"
	"strings"
)

type Uptime struct {
	k8sClient *kubernetes.Clientset
}

const name = "Uptime"

func (u *Uptime) Name() string {
	return name
}

func (u *Uptime) Filter(pod *v1.Pod) bool {
	if pod.Spec.NodeName == "" {
		return false
	}

	uptimeReqStr, ok := pod.Labels["uptime-30d-percentage-request"]
	if !ok {
		return false
	}

	uptimeReq, err := strconv.ParseFloat(strings.TrimSpace(uptimeReqStr), 64)
	if err != nil {
		log.Fatal(err)
	}

	node, err := u.k8sClient.CoreV1().Nodes().Get(context.TODO(), pod.Spec.NodeName, metav1.GetOptions{})
	if err != nil {
		log.Fatal(err)
	}

	nodeUptimeStr, ok := node.Labels["example.com/node-30d-uptime-percentage"]
	if !ok {
		return true
	}

	nodeUptime, err := strconv.ParseFloat(strings.TrimSpace(nodeUptimeStr), 64)
	if err != nil {
		log.Fatal(err)
	}

	if uptimeReq > nodeUptime {
		klog.V(5).Infof("%s uptime request: %f > node uptime: %f", pod.Name, uptimeReq, nodeUptime)
		return true
	}

	return false
}

func New(k8sClient *kubernetes.Clientset) plugins.Evictor {
	log.Printf("Creating new %s plugin\n", name)

	return &Uptime{
		k8sClient: k8sClient,
	}
}
