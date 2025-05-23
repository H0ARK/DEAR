// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { useEffect, useState } from "react";
import { PlusCircle, GitBranch, Trash2, Loader2, Key } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { GitHubTokenDialog } from "./github-token-dialog";

import {
  useRepositoryStore,
  addRepository,
  setCurrentRepository,
  removeRepository,
  type Repository,
  fetchRepositoriesFromGitHub,
} from "~/core/store/repository-store";

export function RepositorySelector() {
  const { repositories, currentRepository, isLoading } = useRepositoryStore();
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [tokenDialogOpen, setTokenDialogOpen] = useState(false);
  const [newRepoUrl, setNewRepoUrl] = useState("");
  const [newRepoError, setNewRepoError] = useState("");
  const [isAddingRepo, setIsAddingRepo] = useState(false);
  const [hasGitHubToken, setHasGitHubToken] = useState(false);

  // State for the new project name dialog
  const [newProjectNameDialogOpen, setNewProjectNameDialogOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectNameError, setNewProjectNameError] = useState("");
  const [isSettingNewProjectName, setIsSettingNewProjectName] = useState(false);

  // Check for GitHub token and load repositories when component mounts
  useEffect(() => {
    const token = localStorage.getItem('github_token');
    setHasGitHubToken(!!token);

    if (token) {
      fetchRepositoriesFromGitHub();
    }
  }, []);

  // Sort repositories by last used date (most recent first)
  const sortedRepositories = [...repositories].sort(
    (a, b) => b.lastUsed.getTime() - a.lastUsed.getTime()
  );

  const handleRepositoryChange = (value: string) => {
    if (value === "add-new") {
      setAddDialogOpen(true);
    } else if (value === "new-project") {
      // Open the dialog to ask for the new project's name
      setNewProjectName("");
      setNewProjectNameError("");
      setNewProjectNameDialogOpen(true);
    } else {
      setCurrentRepository(value);
    }
  };

  const handleAddRepository = async () => {
    setNewRepoError("");
    setIsAddingRepo(true);

    try {
      // Validate URL format
      if (!newRepoUrl.trim()) {
        setNewRepoError("Repository URL is required");
        setIsAddingRepo(false);
        return;
      }

      // Parse GitHub URL
      let owner = "";
      let name = "";

      try {
        const url = new URL(newRepoUrl);
        const pathParts = url.pathname.split("/").filter(Boolean);

        if (url.hostname !== "github.com" || pathParts.length < 2) {
          throw new Error("Invalid GitHub URL");
        }

        if (pathParts[0]) owner = pathParts[0];
        if (pathParts[1]) name = pathParts[1];
      } catch (error) {
        // Try to parse as owner/repo format
        const parts = newRepoUrl.split("/").filter(Boolean);
        if (parts.length !== 2) {
          setNewRepoError("Invalid repository URL or format. Use github.com/owner/repo or owner/repo");
          setIsAddingRepo(false);
          return;
        }
        if (parts[0]) owner = parts[0];
        if (parts[1]) name = parts[1];
      }

      // Validate that we have both owner and name
      if (!owner || !name) {
        setNewRepoError("Invalid repository format. Could not extract owner and name.");
        setIsAddingRepo(false);
        return;
      }

      // Add the repository
      const fullName = `${owner}/${name}`;
      addRepository({
        id: fullName,
        owner,
        name,
        fullName,
        url: `https://github.com/${fullName}`,
      });

      // Close dialog and reset form
      setNewRepoUrl("");
      setAddDialogOpen(false);
    } catch (error) {
      setNewRepoError(`Failed to add repository: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsAddingRepo(false);
    }
  };

  const handleSetNewProjectName = async () => {
    setNewProjectNameError("");
    if (!newProjectName.trim()) {
      setNewProjectNameError("Project name is required.");
      return;
    }
    setIsSettingNewProjectName(true);
    try {
      const projectName = newProjectName.trim();
      const newProjectRepoData: Repository = {
        id: projectName, 
        owner: "_new", 
        name: projectName,
        fullName: projectName, 
        url: `local://project/${projectName}`,
        lastUsed: new Date(),
      };
      
      // Directly set the new project as the current repository in the store
      useRepositoryStore.setState({ currentRepository: newProjectRepoData, isLoading: false });

      setNewProjectName("");
      setNewProjectNameDialogOpen(false);
    } catch (error) {
      setNewProjectNameError(`Failed to set project name: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsSettingNewProjectName(false);
    }
  };

  const handleRemoveRepository = (e: React.MouseEvent, repoId: string) => {
    e.stopPropagation();
    removeRepository(repoId);
  };

  return (
    <div className="flex items-center gap-2">
      <div className="w-64">
        <Select
          value={currentRepository?.id || ""}
          onValueChange={handleRepositoryChange}
          disabled={isLoading}
        >
          <SelectTrigger className="rounded-2xl">
            <SelectValue placeholder="Select a repository">
              {isLoading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Loading...</span>
                </div>
              ) : currentRepository ? (
                <div className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4" />
                  <span>{currentRepository.fullName}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4" />
                  <span>Select a repository</span>
                </div>
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {sortedRepositories.length > 0 && (
              <SelectGroup>
                <SelectLabel>Recent Repositories</SelectLabel>
                {sortedRepositories.map((repo) => (
                  <SelectItem key={repo.id} value={repo.id} className="flex justify-between">
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2">
                        <GitBranch className="h-4 w-4" />
                        <span>{repo.fullName}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={(e) => handleRemoveRepository(e, repo.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </SelectItem>
                ))}
              </SelectGroup>
            )}
            <SelectItem value="add-new">
              <div className="flex items-center gap-2 text-primary">
                <PlusCircle className="h-4 w-4" />
                <span>Add new repository</span>
              </div>
            </SelectItem>
            <SelectItem value="new-project">
              <div className="flex items-center gap-2 text-primary">
                <PlusCircle className="h-4 w-4" />
                <span>Add new project</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* GitHub Token Button */}
      <Button
        variant="outline"
        size="icon"
        className="h-10 w-10 rounded-full"
        onClick={() => setTokenDialogOpen(true)}
        title="Configure GitHub Token"
      >
        <Key className="h-4 w-4" />
      </Button>

      {/* Add Repository Dialog */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add GitHub Repository</DialogTitle>
            <DialogDescription>
              Enter the GitHub repository URL or owner/name format.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="repo-url">Repository URL or owner/name</Label>
              <Input
                id="repo-url"
                placeholder="github.com/owner/repo or owner/repo"
                value={newRepoUrl}
                onChange={(e) => setNewRepoUrl(e.target.value)}
              />
              {newRepoError && (
                <p className="text-sm text-destructive">{newRepoError}</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddRepository} disabled={isAddingRepo}>
              {isAddingRepo ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : (
                "Add Repository"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Project Name Dialog */}
      <Dialog open={newProjectNameDialogOpen} onOpenChange={setNewProjectNameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Name Your New Project</DialogTitle>
            <DialogDescription>
              What would you like to name your new local project? This name will be used to create its workspace.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="new-project-name">Project Name</Label>
              <Input
                id="new-project-name"
                placeholder="e.g., my-awesome-app"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
              />
              {newProjectNameError && (
                <p className="text-sm text-destructive">{newProjectNameError}</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewProjectNameDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSetNewProjectName} disabled={isSettingNewProjectName}>
              {isSettingNewProjectName ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Setting...
                </>
              ) : (
                "Set Project Name"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* GitHub Token Dialog */}
      <GitHubTokenDialog
        open={tokenDialogOpen}
        onOpenChange={setTokenDialogOpen}
      />
    </div>
  );
}
