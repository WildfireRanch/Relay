.PHONY: router-map verify m0
m0: router-map verify

router-map:
	@./ops/bin/dump_router_map.sh

verify:
	@./ops/bin/verify_m0.sh
