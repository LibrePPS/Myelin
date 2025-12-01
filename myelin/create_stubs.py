import pathlib
import sys
import jpype
import stubgenj

jars = list(pathlib.Path('../jars').glob('**/*.jar'))

if not jars:
    print("No jar files found in 'jars' directory")
    sys.exit(1)

classpath = [str(jar) for jar in jars]

print("Starting JVM with classpath...")

# Start JVM with all jars in the classpath
jpype.startJVM(classpath=classpath, convertStrings=True)

# Enable Java imports in Python
import jpype.imports  # noqa

# Import gov java package
import gov  # noqa

print(f"Generating stubs for {len(jars)} jar file(s) ...")

stubgenj.generateJavaStubs([gov], useStubsSuffix=False)

print("Stub generation completed successfully!")