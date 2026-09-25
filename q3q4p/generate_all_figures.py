"""Reproduce final figures 11–25 and LaTeX tables from the bundled final inputs."""
import sys
sys.dont_write_bytecode = True
import matplotlib
matplotlib.use('Agg')
import q3_figures
import q4_figures

if __name__ == '__main__':
    q3_figures.main()
    q4_figures.main()
    print('Finished: 15 figures in PNG/PDF/SVG and LaTeX tables.')
