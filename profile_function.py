import cProfile
import pstats

#Your module here
#from Starfish.parallel import profile_code

#cProfile.run("profile_code()", "prof")

def display_stats(pfile):
    p = pstats.Stats(pfile)
    p.sort_stats('cumulative').print_stats(.2)
    p.sort_stats('time').print_stats(.2)


display_stats('prof')


# Additionally, if you want to do memory profiling using memory_profiler,
# put the decorator `@profile` over the function you want to profile
# And run with
#	python -m memory_profiler model.py
