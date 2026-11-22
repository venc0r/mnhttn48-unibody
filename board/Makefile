.PHONY: fab clean check-baseline check

NAME := mnhttn48-unibody

# JLCPCB PCB order (their KiCad 9 guide): Gerber X2 with Protel extensions (kicad-cli defaults),
# Excellon drills in mm, decimal, absolute origin, PTH and NPTH separate, alternate oval mode.
# F/B.Paste only for a stencil or assembly order.
LAYERS := F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts

fab:
	rm -rf out out.zip
	mkdir -p out
	kicad-cli pcb export gerbers --layers $(LAYERS) --output out/ $(NAME).kicad_pcb
	kicad-cli pcb export drill --format excellon --drill-origin absolute --excellon-units mm \
		--excellon-zeros-format decimal --excellon-oval-format alternate --excellon-separate-th \
		--output out/ $(NAME).kicad_pcb
	zip -rv out.zip out

clean:
	rm -fR out
	rm -f out.zip


check-baseline:
	./check.sh generate check/baseline

check: check/baseline
	./check.sh generate check/current
	./check.sh compare check/baseline check/current
