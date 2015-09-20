MSCGEN ?= mscgen
MSCGEN_FILES =      \
	cache-miss.mscgen \
	cache-hit.mscgen  \
  bulk.mscgen

all: $(MSCGEN_FILES:.mscgen=.png)

clean:
		$(RM) $(MSCGEN_FILES:.mscgen=.png)

.mscgen.png:
	$(MSCGEN) -T png -o $@ $<

.SUFFIXES: .mscgen .png
