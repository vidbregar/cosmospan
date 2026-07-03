package unscheduled

import (
	"github.com/vidbregar/federation-descheduler/pkg/plugins"
	v1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes"
	"log"
)

type Unscheduled struct {
	k8sClient *kubernetes.Clientset
}

const name = "Unscheduled"

func (u *Unscheduled) Name() string {
	return name
}

func (u *Unscheduled) Filter(pod *v1.Pod) bool {
	return pod.Spec.NodeName == ""
}

func New() plugins.Evictor {
	log.Printf("Creating new %s plugin\n", name)

	return &Unscheduled{}
}
