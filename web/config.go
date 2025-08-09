package web

type Config struct {
	Address string `yaml:"address"`
}

// TODO remove static theming support everywhere, we use tailwind for dark mode and can implement a JS based theme switcher
//
