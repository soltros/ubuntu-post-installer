# Managed interactive Zsh configuration. Personal additions stay in ~/.zshrc.
[[ -o interactive ]] || return

typeset -U path
path=("$HOME/.local/bin" "$HOME/.cargo/bin" $path)
export EDITOR=nano VISUAL=nano
HISTFILE="${ZDOTDIR:-$HOME}/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt append_history inc_append_history hist_ignore_dups hist_ignore_space
setopt auto_cd interactive_comments
bindkey -e
bindkey '^[[A' up-line-or-search
bindkey '^[[B' down-line-or-search

export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME=""
plugins=(git sudo)
zstyle ':omz:update' mode disabled
if [[ -r "$ZSH/oh-my-zsh.sh" ]]; then
    source "$ZSH/oh-my-zsh.sh"
else
    autoload -Uz compinit && compinit
    autoload -Uz colors && colors
    print -u2 'Soltros: Oh My Zsh is missing; run sudo bash run.sh --shell-only from your installer checkout.'
fi

# Ubuntu names these binaries batcat and fdfind.
if (( $+commands[bat] )); then
    alias cat='bat --paging=never'
elif (( $+commands[batcat] )); then
    alias bat=batcat
    alias cat='batcat --paging=never'
fi
if (( ! $+commands[fd] && $+commands[fdfind] )); then
    alias fd=fdfind
    alias find=fdfind
elif (( $+commands[fd] )); then
    alias find=fd
fi
(( $+commands[rg] )) && alias grep=rg
(( $+commands[duf] )) && alias df=duf
if (( $+commands[eza] )); then
    alias ls='eza --icons=auto'
    alias ll='eza -la --icons=auto --git'
    alias tree='eza --tree --icons=auto'
fi

# APT equivalents for system/package maintenance.
alias apt-update='sudo apt-get update'
alias apt-upgrade='sudo apt-get upgrade'
alias apt-install='sudo apt-get install'
alias apt-remove='sudo apt-get remove'
alias apt-search='apt-cache search'
alias apt-show='apt-cache show'
alias apt-list='apt list --installed'
alias update='sudo apt-get update && sudo apt-get upgrade'
alias upgrade='sudo apt-get upgrade'
alias ugc='sudo apt-get autoremove --purge && sudo apt-get autoclean'

# Reapply this checkout, refresh it, or refresh and reapply it.
urb() { sudo bash "$SOLTROS_INSTALLER_DIR/run.sh" "$@"; }
ufu() { command git -C "$SOLTROS_INSTALLER_DIR" pull --ff-only && sudo apt-get update; }
ufu-rebuild() { ufu && urb "$@"; }
alias-help() {
    local name
    printf '%-22s %s\n' 'ALIAS' 'COMMAND'
    for name in ${(ok)aliases}; do
        printf '%-22s %s\n' "$name" "$aliases[$name]"
    done
    printf '\nurb [options]          Reapply the workstation profile\n'
    printf 'ufu                    Update this checkout and APT indexes\n'
    printf 'ufu-rebuild [options]  Update and reapply the profile\n'
}
alias aliases=alias-help
alias alises=alias-help

# Autosuggestions and highlighting must load after the framework.
[[ ! -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]] || source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
[[ ! -r /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]] || source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

# Initialize last so an earlier theme/prompt cannot override Starship.
if (( $+commands[starship] )); then
    eval "$(starship init zsh)"
else
    print -u2 'Soltros: Starship is missing. Install it with sudo apt install starship, then exec zsh.'
fi
