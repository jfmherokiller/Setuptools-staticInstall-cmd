import distutils.cmd
import distutils.log
import distutils.extension
import re
import shutil
import sys

import setuptools
import subprocess
import os


class StaticPythonSetup(distutils.cmd.Command):
    """A custom command to setup Extension for StaticInclusion."""

    description = 'Make Static Includable extension'
    user_options = [
        # The format is (long option, short option, description).
        ('OutputDir=', None, 'path to Output Files'),
    ]

    def initialize_options(self):
        """Set default values for options."""
        # Each user option must be listed here with their default value.
        pass

    def finalize_options(self):
        """Post-process options."""
        pass

    def run(self):
        """Run command."""
        ProjectName = ''.join(e for e in self.distribution.metadata.name if (e.isalnum() or e == "_")).lower()
        self.MakeDirs(ProjectName)
        self.CopyFiles(ProjectName)
        NameReplacements = self.GenerateNameReplacements()
        NameReplacements = self.OrganizeImports(NameReplacements)
        InitLines = self.InitFileContents(ProjectName, NameReplacements)
        self.PatchFiles(NameReplacements)
        self.SetupFile(ProjectName, NameReplacements)
        self.Generate_c_Files(NameReplacements)

    def PatchFiles(self, NameReplacements):
        Source_Mod = "src_mod/"
        for File in os.listdir(Source_Mod):
            if File.endswith(".c") or File.endswith(".h") or File.endswith(".cpp"):
                continue
            RealFile = Source_Mod + File
            BaseName = os.path.splitext(File)[0]
            BaseExtentsion = os.path.splitext(File)[1]
            RealNewFile = next((ReplacementName[2] for i, ReplacementName in enumerate(NameReplacements) if
                                BaseName == ReplacementName[1]), BaseName)
            RealNewFile = RealNewFile + BaseExtentsion
            RealNewFile = Source_Mod + RealNewFile
            if File.endswith(".pxi"):
                RealNewFile = RealFile
            with open(RealFile, "r") as fd:
                source = fd.read()
            os.remove(RealFile)
            for Name in NameReplacements:
                source = source.replace("cimport " + Name[1] + " as", "cimport " + Name[2] + " as")
                source = source.replace("cimport " + Name[1] + "\n", "cimport " + Name[2] + " as " + Name[1] + "\n")
                source = source.replace("from " + Name[0] + " cimport", "from " + Name[1] + " cimport")
                source = source.replace("cimport " + Name[0], "cimport " + Name[2])
                source = source.replace("from " + Name[0] + " import", "from " + Name[2] + " import")
                source = source.replace("from " + Name[1] + " cimport", "from " + Name[2] + " cimport")
                source = source.replace("\nimport " + Name[1] + "\n", "\nimport " + Name[2] + " as " + Name[1] + "\n")

            with open(RealNewFile, "w") as fd:
                fd.write(source)

    def OrganizeImports(self, ImportsToSort):
        from collections import defaultdict

        class Graph:
            def __init__(self):
                self.graph = defaultdict(list)  # dictionary containing adjacency List

            # function to add an edge to graph
            def addEdge(self, u, v):
                self.graph[u].append(v)

            def getVerts(self):
                return len(self.graph)

            # A recursive function used by topologicalSort
            def topologicalSortUtil(self, v, visited, stack):

                # Mark the current node as visited.
                visited[v] = True

                # Recur for all the vertices adjacent to this vertex
                for i in self.graph[v]:
                    if i != '' and (i in list(self.graph)):
                        if not visited[i]:
                            self.topologicalSortUtil(i, visited, stack)

                        # Push current vertex to stack which stores result
                stack.insert(0, v)

                # The function to do Topological Sort. It uses recursive

            # topologicalSortUtil()
            def topologicalSort(self):
                # Mark all the vertices as not visited
                visited = {}
                for i in list(self.graph):
                    visited[i] = False
                stack = []

                # Call the recursive helper function to store Topological
                # Sort starting from all vertices one by one
                for i in list(self.graph):
                    if not visited[i]:
                        self.topologicalSortUtil(i, visited, stack)
                    # Print contents of the stack
                return stack

        Source_Mod = "src_mod/"
        Mygraph = Graph()
        FileImportLists = []
        for File in os.listdir(Source_Mod):
            FileEntry = os.path.splitext(File)[0]
            ListOfImports = []
            RealFile = Source_Mod + File
            # get all imports and build small trees
            with open(RealFile, "rt") as FileD:
                source = FileD.read()
            for match in re.finditer(r"from (.*) cimport ", source):
                Mymatch = match.group(1).split(".").pop()
                if ("libc." not in match.group(1)) and ("cpython." not in match.group(1)):
                    ListOfImports.append([Mymatch, match.group(1)])
            for match in re.finditer(r"cimport (.*) as ", source):
                Mymatch = match.group(1).split(".").pop()
                if ("libc." not in match.group(1)) and ("cpython." not in match.group(1)):
                    ListOfImports.append([Mymatch, match.group(1)])
            for match in re.finditer(r"cimport (.*) \n", source):
                Mymatch = match.group(1).split(".").pop()
                if ("libc." not in match.group(1)) and ("cpython." not in match.group(1)):
                    ListOfImports.append([Mymatch, match.group(1)])
            for match in re.finditer(r"include \"(.*)\"|include (.*)\n", source):
                Mymatch = match.group(1).split(".")[0]
                if ("libc." not in match.group(1)) and ("cpython." not in match.group(1)):
                    ListOfImports.append([Mymatch, match.group(1)])
            FileImportLists.append(([FileEntry, File], ListOfImports))
        # pre sort based upon length of imports
        FileImportLists.sort(key=lambda tup: len(tup[1]))
        # add to graph for final sorting
        for FileList in FileImportLists:
            Name = FileList[0][0]
            Mygraph.addEdge(Name, "")
            for Import in FileList[1]:
                GraphImport = Import[0]
                Mygraph.addEdge(Name, GraphImport)
        Indexes = Mygraph.topologicalSort()
        Indexes.reverse()

        def GetIndex(Item):
            return Indexes.index(Item[1])

        FinalList = sorted(ImportsToSort, key=GetIndex)
        return FinalList

    def PerformReplacement(self, StrToParse):
        NewName = "__cwrap_" + StrToParse.replace(".", "_")
        return NewName

    def GenerateNameReplacements(self):
        Replacements = []
        for ext in self.distribution.ext_modules:
            NewName = self.PerformReplacement(ext.name)
            Replacement = [ext.name, ext.name.split(".").pop(), NewName]
            Replacements.append(Replacement)
        return Replacements

    def MakeDirs(self, ProjectName):
        if os.path.isdir("src_mod"):
            shutil.rmtree("src_mod")
        if os.path.isdir("build_mod"):
            shutil.rmtree("build_mod")

        os.makedirs("src_mod")
        os.makedirs("build_mod/c_files")
        os.makedirs("build_mod/" + ProjectName)
        os.makedirs("build_mod/setup")

    def CopyFiles(self, ProjectName):
        RealFiles = []
        import glob
        for filename in glob.iglob((os.getcwd() + "/../") + '**/**/*', recursive=True):
            if ProjectName in os.path.abspath(filename):
                if (filename.endswith(".pyx") or filename.endswith(".pxd") or
                        filename.endswith(".pxi") or filename.endswith(".c") or
                        filename.endswith(".cpp") or filename.endswith(".h")):
                    if ("/build/" not in filename) and ("/gen/" not in filename):
                        RealFiles.append(os.path.abspath(filename))
                    if "/gen/" in filename:
                        if (filename.endswith(".pyx") or filename.endswith(".pxd") or
                                filename.endswith(".pxi")):
                            RealFiles.append(os.path.abspath(filename))
        for File in RealFiles:
            if File.endswith(".c") or File.endswith(".cpp") or File.endswith(".h"):
                shutil.copy2(File, "build_mod/c_files/")
            if File.endswith(".pyx") or File.endswith(".pxd") or File.endswith(".pxi"):
                shutil.copy2(File, "build_mod/" + ProjectName + "/")
                shutil.copy2(File, "src_mod/")

    def InitFileContents(self, ProjectName, Names):
        InitFileLines = []
        for Name in Names:
            TopLine = "import " + Name[2]
            SecondLine = "sys.modules[\'" + Name[0] + "\']" + " = " + Name[2]
            Fullline = TopLine + "\n" + SecondLine
            InitFileLines.append(Fullline)
            with open("build_mod/setup/" + ProjectName + ".txt", "w") as f:
                for Line in InitFileLines:
                    f.write(Line + "\n")
        return InitFileLines

    def SetupFile(self, ProjectName, NameReplacements):
        with open("build_mod/setup/" + ProjectName + ".setup", "w") as f:
            for ext in NameReplacements:
                RealExt = next(v for i, v in enumerate(self.distribution.ext_modules) if ext[0] in v.name)
                # Combine Sources
                RealSources = []
                for Source in RealExt.sources:
                    if os.path.basename(os.path.splitext(Source)[0]) == ext[0]:
                        Src_ext = os.path.splitext(Source)[1]
                        ConvertedSource = ext[2] + Src_ext
                        Source = ConvertedSource
                    RealSources.append(os.path.basename(Source))
                RealSources = " ".join(RealSources)
                # make the includeLines
                IncludeLines = []
                for Include in RealExt.include_dirs:
                    IncludeLines.append("-I" + Include)
                # Make the libraryDirs
                LibraryDirs = []
                for LibDir in RealExt.library_dirs:
                    LibraryDirs.append("-L" + LibDir)
                Libs = []
                # Make Lib Lines
                for Library in RealExt.libraries:
                    Libs.append("-l" + Library)
                Defines = []
                for Define in RealExt.define_macros:
                    if Define[1] != "":
                        Defines.append("-D"+Define[0]+"="+str(Define[1]))
                    else:
                        Defines.append("-D"+Define[0])
                UnDefines = []
                for Undefine in RealExt.undef_macros:
                    UnDefines.append("-U"+Undefine)
                CompleteLibs = " ".join(LibraryDirs) + " " + " ".join(Libs)
                NameAndSrc = ext[2] + " " + RealSources

                NameAndSrcAndIncludes = NameAndSrc + " " + " ".join(IncludeLines)
                DefinesAndUndefines = " " + " ".join(Defines) + " " + " ".join(UnDefines)
                NameAndSrcAndIncludesAndDefines = NameAndSrcAndIncludes + DefinesAndUndefines
                FinalLine = NameAndSrcAndIncludesAndDefines + " " + CompleteLibs
                FinalLine = " ".join(FinalLine.split())

                f.write(FinalLine + "\n")

    def Generate_c_Files(self, NameReplacements):
        for Name in NameReplacements:
            self.cython_new(Name)

    def cython_new(self, name):
        """
        Compiles a cython module. This takes care of regenerating it as necessary
        when it, or any of the files it depends on, changes.
        """

        fn = "src_mod/" + name[2] + ".pyx"
        print("generating", name[0])
        try:
            subprocess.check_call([
                "cython",
                "-Iinclude",
                "-I" + "src_mod",
                # "-a",
                fn,
                "-o",
                "build_mod/c_files/"
            ])

        except subprocess.CalledProcessError as e:
            print()
            print(str(e))
            print()
            sys.exit(-1)
