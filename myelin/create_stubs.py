import pathlib
import sys
import jpype # pyright: ignore[reportMissingTypeStubs]
import stubgenj # pyright: ignore[reportMissingTypeStubs]

jars = list(pathlib.Path("../jars").glob("**/*.jar"))

if not jars:
    print("No jar files found in 'jars' directory")
    sys.exit(1)

classpath = [str(jar) for jar in jars]

print("Starting JVM with classpath...")

# Start JVM with all jars in the classpath for stub generation
jpype.startJVM(classpath=classpath, convertStrings=True) # pyright: ignore[reportUnknownMemberType]

# Enable Java imports in Python
import jpype.imports  #noqa # pyright: ignore[reportMissingTypeStubs, reportUnusedImport]

# Stubs for java.util without this all java.util methods will be marked as partially unknown
import java.util  # noqa

# Import gov java package (CMS Java jars are in this namespace)
import gov  # noqa

print(f"Generating stubs for {len(jars)} jar file(s) ...")

stubgenj.generateJavaStubs([gov, java.util], useStubsSuffix=False) # pyright: ignore[reportArgumentType]

print("Stub generation completed successfully!")
