MSCGEN ?= mscgen
MSCGEN_FILES = \
	straightforward.mscgen

all: $(MSCGEN_FILES:.mscgen=.png)

clean:
		$(RM) $(MSCGEN_FILES:.mscgen=.png)

.mscgen.png:
	$(MSCGEN) -T png -o $@ $<

.SUFFIXES: .mscgen .png
