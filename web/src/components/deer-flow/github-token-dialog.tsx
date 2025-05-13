// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { useState, useEffect } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";

import { fetchRepositoriesFromGitHub } from "~/core/store/repository-store";
import { LoadingOutlined } from "@ant-design/icons";

const GITHUB_TOKEN_KEY = "github_token";

export function GitHubTokenDialog({
  trigger,
  open,
  onOpenChange,
}: {
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [token, setToken] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  // Use controlled state if provided, otherwise use internal state
  const isOpen = open !== undefined ? open : dialogOpen;
  const setIsOpen = onOpenChange || setDialogOpen;

  // Load token from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem(GITHUB_TOKEN_KEY);
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  const handleSaveToken = async () => {
    if (!token.trim()) {
      toast.error("Please enter a GitHub token");
      return;
    }

    setIsLoading(true);
    
    try {
      // Validate token by making a test API call
      const response = await fetch("https://api.github.com/user", {
        headers: {
          Authorization: `token ${token}`,
          Accept: "application/vnd.github.v3+json",
        },
      });

      if (!response.ok) {
        throw new Error(`GitHub API error: ${response.status}`);
      }

      // Save token to localStorage
      localStorage.setItem(GITHUB_TOKEN_KEY, token);

      // Fetch repositories using the token
      await fetchRepositoriesFromGitHub();

      toast.success("GitHub token saved successfully");
      setIsOpen(false);
    } catch (error) {
      console.error("Error validating GitHub token:", error);
      toast.error("Invalid GitHub token. Please check and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent>
        <DialogHeader>
          <DialogTitle>GitHub Token</DialogTitle>
          <DialogDescription>
            Enter your GitHub personal access token to enable repository access.
            The token needs 'repo' scope permissions.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="github-token">GitHub Token</Label>
            <Input
              id="github-token"
              type="password"
              placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSaveToken} disabled={isLoading}>
            {isLoading ? (
              <>
                <LoadingOutlined className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Token"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
