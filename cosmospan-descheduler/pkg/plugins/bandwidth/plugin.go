package bandwidth

import (
	"log"
	"strconv"
	"strings"

	"github.com/vidbregar/federation-descheduler/pkg/plugins"
	v1 "k8s.io/api/core/v1"
)

type Bandwidth struct {
	snapshot map[string]*State
}

const name = "Bandwidth"

func (b *Bandwidth) Name() string {
	return name
}

func (b *Bandwidth) Filter(pod *v1.Pod) bool {
	node := pod.Spec.NodeName

	state, ok := b.snapshot[node]
	if !ok {
		// something weird must be happening, let's deschedule just to be sure
		return true
	}

	var err error

	var ingressReq float64
	ingressReqStr, ok := pod.Labels["ingress-bandwidth-request-Mbps"]
	if ok {
		ingressReq, err = strconv.ParseFloat(strings.TrimSpace(ingressReqStr), 64)
		if err != nil {
			log.Fatalf("Error converting ingress request to float: %s", err.Error())
		}
	}

	var egressReq float64
	egressReqStr, ok := pod.Labels["egress-bandwidth-request-Mbps"]
	if ok {
		egressReq, err = strconv.ParseFloat(strings.TrimSpace(egressReqStr), 64)
		if err != nil {
			log.Fatalf("Error converting egress request to float: %s", err.Error())
		}

	}

	const epsilon = 10e-9
	if (ingressReq > 0 || egressReq > 0) &&
		(state.TotalIngressReqs > (state.IngressCap-epsilon) ||
			state.TotalEgressReqs > (state.EgressCap-epsilon)) {

		// assume pod is deleted
		state.TotalIngressReqs -= ingressReq
		state.TotalEgressReqs -= egressReq
		return true
	}

	return false
}

func New(snapshot map[string]*State) plugins.Evictor {
	log.Printf("Creating new %s plugin\n", name)

	return &Bandwidth{
		snapshot: snapshot,
	}
}
