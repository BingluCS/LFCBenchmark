"""Shared layout for a compact row of dataset plots."""

import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, MaxNLocator, NullLocator


def panel_row(count, *, sharey=False):
    width = 2.4 * count + 0.6
    fig, axes = plt.subplots(1, count, figsize=(width, 3.05), squeeze=False, sharey=sharey)
    fig.subplots_adjust(left=0.85 / width, right=1 - 0.16 / width,
                        bottom=0.2, top=0.76, wspace=0.35)
    return fig, axes[0]


def compact_axis(ax, title):
    ax.set(xlabel="", ylabel="")
    ax.set_title(title, fontsize=10, pad=6)
    ax.tick_params(axis="both", labelsize=8, pad=2)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=3))
    if ax.get_yscale() == "log":
        ax.yaxis.set_major_locator(LogLocator(numticks=5))
        ax.yaxis.set_minor_locator(NullLocator())
    elif ax.get_yscale() == "symlog":
        ax.yaxis.get_major_locator().set_params(numticks=5)
        ax.yaxis.set_minor_locator(NullLocator())
    else:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))


def label_row(fig, xlabel, ylabel):
    fig.supxlabel(xlabel, y=0.035, fontsize=9.5)
    fig.supylabel(ylabel, x=0.015, y=0.48, fontsize=9.5)
