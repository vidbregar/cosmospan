package plugins

import v1 "k8s.io/api/core/v1"

type Plugin interface {
	Name() string
}

type Evictor interface {
	Plugin
	// Filter checks if a pod can be evicted
	Filter(pod *v1.Pod) bool
}
